package io.jenkins.plugins.darkmoon;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.cloudbees.plugins.credentials.CredentialsScope;
import com.cloudbees.plugins.credentials.SystemCredentialsProvider;
import hudson.model.Result;
import hudson.util.Secret;
import io.jenkins.plugins.analysis.core.model.ResultAction;
import java.io.File;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.jenkinsci.plugins.plaincredentials.impl.StringCredentialsImpl;
import org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition;
import org.jenkinsci.plugins.workflow.job.WorkflowJob;
import org.jenkinsci.plugins.workflow.job.WorkflowRun;
import org.junit.jupiter.api.Test;
import org.jvnet.hudson.test.JenkinsRule;
import org.jvnet.hudson.test.junit.jupiter.WithJenkins;

@WithJenkins
class DarkmoonScanStepJenkinsTest {

    private static final String SECRET = "dm-supersecret-TOKEN-abc123";
    private static final String[] FAKE_FILES = {
        "fake-darkmoon-ci.sh", "findings.json", "summary.json", "status.json", "report.md"
    };

    private Path stageFakeCli() throws Exception {
        Path dir = Files.createTempDirectory("darkmoon-fake-cli");
        for (String name : FAKE_FILES) {
            try (InputStream in = getClass().getResourceAsStream("/fake-cli/" + name)) {
                Files.copy(in, dir.resolve(name));
            }
        }
        File script = dir.resolve("fake-darkmoon-ci.sh").toFile();
        assertTrue(script.setExecutable(true, false));
        return dir;
    }

    private String addTokenCredential(JenkinsRule j) throws Exception {
        StringCredentialsImpl c = new StringCredentialsImpl(
                CredentialsScope.GLOBAL, "dm-token", "Darkmoon token", Secret.fromString(SECRET));
        SystemCredentialsProvider.getInstance().getCredentials().add(c);
        SystemCredentialsProvider.getInstance().save();
        return "dm-token";
    }

    private WorkflowJob job(JenkinsRule j, String name, String pipeline) throws Exception {
        WorkflowJob p = j.jenkins.createProject(WorkflowJob.class, name);
        p.setDefinition(new CpsFlowDefinition(pipeline, true));
        return p;
    }

    private String pipeline(Path fakeDir, String cliScript, String failOn, String unstableOn, boolean recordIssues) {
        return "node {\n"
                + "  withEnv(['DARKMOON_FAKE_DIR=" + fakeDir.toString() + "']) {\n"
                + "    darkmoonScan target: 'http://app:3000', mode: 'oss', failOn: '" + failOn + "',\n"
                + "      unstableOn: '" + unstableOn + "', credentialsId: 'dm-token',\n"
                + "      cliPath: '" + cliScript + "', ossDataDir: 'ignored',\n"
                + "      recordIssues: " + recordIssues + ", archiveReport: true\n"
                + "  }\n"
                + (recordIssues
                        ? "  recordIssues(enabledForFailure: true, "
                                + "tools: [sarif(pattern: 'darkmoon-reports/darkmoon.sarif')])\n"
                        : "")
                + "}\n";
    }

    @Test
    void failsBuildAndPublishesIssues(JenkinsRule j) throws Exception {
        Path fake = stageFakeCli();
        addTokenCredential(j);
        String script = fake.resolve("fake-darkmoon-ci.sh").toString();

        WorkflowJob p = job(j, "dm-fail", pipeline(fake, script, "high", "none", true));
        WorkflowRun run = p.scheduleBuild2(0).get();

        // Fail policy: 2 critical + 1 high >= high -> FAILURE.
        j.assertBuildStatus(Result.FAILURE, run);
        String log = j.getLog(run);
        assertTrue(log.contains("critical=2, high=1, medium=2"), "redaction-safe counts in console");
        assertTrue(log.contains("marking build FAILURE"));

        // Archived artifacts (internal): report + sarif + ci log.
        assertTrue(run.getArtifactManager().root().child("darkmoon-reports/darkmoon.sarif").exists());
        assertTrue(run.getArtifactManager().root().child("darkmoon-reports/darkmoon-report.md").exists());
        assertTrue(run.getArtifactManager().root().child("darkmoon-reports/darkmoon-ci.log").exists());

        // warnings-ng mapped the SARIF to 5 issues.
        ResultAction action = run.getAction(ResultAction.class);
        assertTrue(action != null, "warnings-ng ResultAction present");
        assertEquals(5, action.getResult().getIssues().size());

        // Secret hygiene: token reached the CLI via env, but NEVER the console log.
        String receivedToken = Files.readString(fake.resolve("received_token.txt"));
        assertEquals(SECRET, receivedToken, "token passed to CLI via environment");
        assertFalse(log.contains(SECRET), "secret must never appear in the build log");
    }

    @Test
    void passesWhenBelowThreshold(JenkinsRule j) throws Exception {
        Path fake = stageFakeCli();
        addTokenCredential(j);
        String script = fake.resolve("fake-darkmoon-ci.sh").toString();

        // failOn none, unstableOn none -> SUCCESS regardless of findings.
        WorkflowJob p = job(j, "dm-pass", pipeline(fake, script, "none", "none", false));
        WorkflowRun run = p.scheduleBuild2(0).get();
        j.assertBuildStatus(Result.SUCCESS, run);
        assertTrue(j.getLog(run).contains("Fail policy not triggered"));
    }

    @Test
    void unstableWhenMediumThreshold(JenkinsRule j) throws Exception {
        Path fake = stageFakeCli();
        addTokenCredential(j);
        String script = fake.resolve("fake-darkmoon-ci.sh").toString();

        WorkflowJob p = job(j, "dm-unstable", pipeline(fake, script, "none", "medium", false));
        WorkflowRun run = p.scheduleBuild2(0).get();
        j.assertBuildStatus(Result.UNSTABLE, run);
        assertTrue(j.getLog(run).contains("marking build UNSTABLE"));
    }
}
