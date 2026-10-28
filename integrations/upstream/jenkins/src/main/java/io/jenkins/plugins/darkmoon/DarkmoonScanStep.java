package io.jenkins.plugins.darkmoon;

import com.cloudbees.plugins.credentials.CredentialsMatchers;
import com.cloudbees.plugins.credentials.CredentialsProvider;
import com.cloudbees.plugins.credentials.common.StandardListBoxModel;
import com.cloudbees.plugins.credentials.domains.URIRequirementBuilder;
import edu.umd.cs.findbugs.annotations.CheckForNull;
import edu.umd.cs.findbugs.annotations.NonNull;
import hudson.AbortException;
import hudson.EnvVars;
import hudson.Extension;
import hudson.FilePath;
import hudson.Launcher;
import hudson.model.AbstractProject;
import hudson.model.Item;
import hudson.model.Queue;
import hudson.model.Result;
import hudson.model.Run;
import hudson.model.TaskListener;
import hudson.security.ACL;
import hudson.tasks.ArtifactArchiver;
import hudson.tasks.BuildStepDescriptor;
import hudson.tasks.Builder;
import hudson.util.FormValidation;
import hudson.util.ListBoxModel;
import io.jenkins.plugins.darkmoon.cli.DarkmoonCliRunner;
import io.jenkins.plugins.darkmoon.contract.CliJson;
import io.jenkins.plugins.darkmoon.contract.Finding;
import io.jenkins.plugins.darkmoon.contract.Severity;
import io.jenkins.plugins.darkmoon.contract.SeveritySummary;
import io.jenkins.plugins.darkmoon.contract.Verdict;
import io.jenkins.plugins.darkmoon.sarif.SarifWriter;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.StringJoiner;
import jenkins.model.Jenkins;
import jenkins.tasks.SimpleBuildStep;
import org.jenkinsci.Symbol;
import org.jenkinsci.plugins.plaincredentials.StringCredentials;
import org.kohsuke.stapler.AncestorInPath;
import org.kohsuke.stapler.DataBoundConstructor;
import org.kohsuke.stapler.DataBoundSetter;
import org.kohsuke.stapler.QueryParameter;

/**
 * {@code darkmoonScan} build/pipeline step: runs a Darkmoon penetration-test
 * campaign via the portable {@code darkmoon-ci} CLI (OSS or Pro), maps the
 * normalized findings to SARIF for Warnings Next Generation, archives the report
 * internally, prints a redaction-safe summary, and applies a fail policy.
 *
 * <p>Owns the Jenkins concerns (credentials, step config, result publishing);
 * delegates the OSS/Pro contract entirely to {@code darkmoon-ci}.
 */
public class DarkmoonScanStep extends Builder implements SimpleBuildStep {

    private final String target;

    private String mode = "auto";
    private String apiUrl;
    private String credentialsId;
    private String licenseCredentialsId;
    private String failOn = "high";
    private String unstableOn = "none";
    private boolean recordIssues = true;
    private boolean archiveReport = true;
    private boolean includeFullReport = false;
    private String cliPath = "bundled";
    private int timeout;
    private String outputDir = "darkmoon-reports";
    private String extraArgs = "";
    private String ossDataDir;
    private String ossReportsDir;
    private String ossScript;

    @DataBoundConstructor
    public DarkmoonScanStep(@NonNull String target) {
        this.target = target;
    }

    public String getTarget() {
        return target;
    }

    public String getMode() {
        return mode;
    }

    @DataBoundSetter
    public void setMode(String mode) {
        this.mode = (mode == null || mode.isBlank()) ? "auto" : mode.trim();
    }

    @CheckForNull
    public String getApiUrl() {
        return apiUrl;
    }

    @DataBoundSetter
    public void setApiUrl(String apiUrl) {
        this.apiUrl = apiUrl;
    }

    @CheckForNull
    public String getCredentialsId() {
        return credentialsId;
    }

    @DataBoundSetter
    public void setCredentialsId(String credentialsId) {
        this.credentialsId = credentialsId;
    }

    @CheckForNull
    public String getLicenseCredentialsId() {
        return licenseCredentialsId;
    }

    @DataBoundSetter
    public void setLicenseCredentialsId(String licenseCredentialsId) {
        this.licenseCredentialsId = licenseCredentialsId;
    }

    public String getFailOn() {
        return failOn;
    }

    @DataBoundSetter
    public void setFailOn(String failOn) {
        this.failOn = (failOn == null || failOn.isBlank()) ? "none" : failOn.trim().toLowerCase();
    }

    public String getUnstableOn() {
        return unstableOn;
    }

    @DataBoundSetter
    public void setUnstableOn(String unstableOn) {
        this.unstableOn = (unstableOn == null || unstableOn.isBlank()) ? "none" : unstableOn.trim().toLowerCase();
    }

    public boolean isRecordIssues() {
        return recordIssues;
    }

    @DataBoundSetter
    public void setRecordIssues(boolean recordIssues) {
        this.recordIssues = recordIssues;
    }

    public boolean isArchiveReport() {
        return archiveReport;
    }

    @DataBoundSetter
    public void setArchiveReport(boolean archiveReport) {
        this.archiveReport = archiveReport;
    }

    public boolean isIncludeFullReport() {
        return includeFullReport;
    }

    @DataBoundSetter
    public void setIncludeFullReport(boolean includeFullReport) {
        this.includeFullReport = includeFullReport;
    }

    public String getCliPath() {
        return cliPath;
    }

    @DataBoundSetter
    public void setCliPath(String cliPath) {
        this.cliPath = (cliPath == null || cliPath.isBlank()) ? "darkmoon-ci" : cliPath.trim();
    }

    public int getTimeout() {
        return timeout;
    }

    @DataBoundSetter
    public void setTimeout(int timeout) {
        this.timeout = Math.max(0, timeout);
    }

    public String getOutputDir() {
        return outputDir;
    }

    @DataBoundSetter
    public void setOutputDir(String outputDir) {
        this.outputDir = (outputDir == null || outputDir.isBlank()) ? "darkmoon-reports" : outputDir.trim();
    }

    public String getExtraArgs() {
        return extraArgs;
    }

    @DataBoundSetter
    public void setExtraArgs(String extraArgs) {
        this.extraArgs = extraArgs == null ? "" : extraArgs.trim();
    }

    @CheckForNull
    public String getOssDataDir() {
        return ossDataDir;
    }

    @DataBoundSetter
    public void setOssDataDir(String ossDataDir) {
        this.ossDataDir = ossDataDir;
    }

    @CheckForNull
    public String getOssReportsDir() {
        return ossReportsDir;
    }

    @DataBoundSetter
    public void setOssReportsDir(String ossReportsDir) {
        this.ossReportsDir = ossReportsDir;
    }

    @CheckForNull
    public String getOssScript() {
        return ossScript;
    }

    @DataBoundSetter
    public void setOssScript(String ossScript) {
        this.ossScript = ossScript;
    }

    /** SARIF path (workspace-relative) for {@code recordIssues(tools:[sarif(pattern:...)])}. */
    public String sarifPattern() {
        return outputDir + "/darkmoon.sarif";
    }

    @Override
    public void perform(
            @NonNull Run<?, ?> run,
            @NonNull FilePath workspace,
            @NonNull EnvVars env,
            @NonNull Launcher launcher,
            @NonNull TaskListener listener)
            throws InterruptedException, IOException {

        String relativeOutput = env.expand(outputDir).replace('\\', '/');
        if (relativeOutput.isBlank() || java.util.Arrays.asList(relativeOutput.split("/")).contains(".") || relativeOutput.startsWith("/") || relativeOutput.matches("^[A-Za-z]:.*") ||
                java.util.Arrays.asList(relativeOutput.split("/")).contains("..") || relativeOutput.contains("*") || relativeOutput.contains("?")) {
            throw new AbortException("Output directory must be a workspace-relative directory without traversal or glob characters.");
        }
        FilePath out = workspace.child(relativeOutput);
        out.mkdirs();
        for (String name : List.of("darkmoon.sarif", "darkmoon-report.md", "darkmoon-report-full.md", DarkmoonCliRunner.LOG_FILE)) out.child(name).delete();

        String resolvedApiUrl = apiUrl == null ? null : env.expand(apiUrl);
        String token = resolveSecret(run, credentialsId, resolvedApiUrl, listener, "token");
        String license = resolveSecret(run, licenseCredentialsId, resolvedApiUrl, listener, "license");

        List<String> extra = new ArrayList<>();
        if (extraArgs != null && !extraArgs.isBlank()) {
            String[] tokens = hudson.Util.tokenize(env.expand(extraArgs));
            java.util.Set<String> allowed = java.util.Set.of("--program", "--focus", "--severity", "--exclude", "--out-of-scope", "--poll");
            for (int i = 0; i < tokens.length; i += 2) {
                if (!allowed.contains(tokens[i]) || i + 1 >= tokens.length || tokens[i + 1].startsWith("--")) throw new AbortException("Extra arguments must be supported scan options with values; credentials and backend options use dedicated settings.");
                extra.add(tokens[i]); extra.add(tokens[i + 1]);
            }
        }
        List<String> command = null;
        if ("bundled".equals(cliPath) || "darkmoon-ci".equals(cliPath)) {
            FilePath directory = workspace.child(".darkmoon/client"); directory.mkdirs();
            FilePath executable = directory.child("darkmoon-ci.cjs");
            try (InputStream resource = getClass().getResourceAsStream("/darkmoon-client/darkmoon-ci.cjs")) {
                if (resource == null) throw new AbortException("The packaged Darkmoon CLI is missing.");
                executable.copyFrom(resource);
            }
            command = List.of("node", executable.getRemote());
        }

        DarkmoonCliRunner.Options opts = DarkmoonCliRunner.Options.builder()
                .cliPath(env.expand(cliPath))
                .commandTokens(command)
                .target(env.expand(target))
                .mode(mode)
                .apiUrl(resolvedApiUrl)
                .ossDataDir(ossDataDir == null ? null : env.expand(ossDataDir))
                .ossReportsDir(ossReportsDir == null ? null : env.expand(ossReportsDir))
                .ossScript(ossScript == null ? null : env.expand(ossScript))
                .timeoutSeconds(timeout)
                .token(token)
                .license(license)
                .baseEnv(env)
                .extraArgs(extra)
                .build();

        DarkmoonCliRunner runner = new DarkmoonCliRunner(launcher, workspace, out, listener, opts);

        // ---- 1) run: launch + wait + fail-policy verdict (source: findings) ----
        String failOnCsv = failOnCsv();
        DarkmoonCliRunner.Exec runExec;
        try {
            runExec = runner.run(failOnCsv);
        } catch (IOException e) {
            throw new AbortException("The Darkmoon CLI could not be launched; Node and the configured command must be available on the agent.");
        }
        if (runExec.exitCode != 0 && runExec.exitCode != 2) {
            archiveQuietly(run, workspace, env, launcher, listener);
            throw new AbortException("darkmoon-ci 'run' failed (exit 1). See the archived "
                    + outputDir + "/" + DarkmoonCliRunner.LOG_FILE + " for execution status.");
        }

        Verdict verdict;
        try {
            verdict = CliJson.parseVerdict(runExec.stdout);
        } catch (IOException e) {
            // Diagnostic exposes only the response shape, never response bodies,
            // secrets, campaign IDs or other untrusted CLI data.
            String raw = runExec.stdout == null ? "" : runExec.stdout;
            listener.getLogger().println("[darkmoon] Invalid CLI run response (chars=" + raw.length()
                    + ", object=" + raw.stripLeading().startsWith("{")
                    + ", campaignId-field=" + raw.contains("\"campaignId\"")
                    + ", verdict-field=" + raw.contains("\"verdict\"") + ").");
            throw new AbortException("Could not parse the CLI run verdict; no trustworthy assessment result is available.");
        }
        String campaignId = verdict.getCampaignId();
        if (campaignId == null || campaignId.isBlank()) {
            throw new AbortException("darkmoon-ci did not return a campaign id.");
        }
        listener.getLogger().println("[darkmoon] campaign " + campaignId
                + " — CLI verdict: " + (verdict.failed() ? "FAIL" : "PASS"));
        DarkmoonCliRunner.Exec statusExec = runner.status(campaignId);
        if (statusExec.exitCode != 0) throw new AbortException("Campaign status could not be read.");
        io.jenkins.plugins.darkmoon.contract.Campaign completed;
        try { completed = CliJson.parseCampaign(statusExec.stdout); }
        catch (IOException error) { throw new AbortException("Campaign status document is invalid."); }
        if (!campaignId.equals(completed.getId()) || !"completed".equals(completed.getStatus())) throw new AbortException("The requested assessment has not completed successfully; no findings verdict is available.");

        // Findings must be readable and valid before publishing any scan result.
        DarkmoonCliRunner.Exec findExec = runner.findings(campaignId);
        if (findExec.exitCode != 0) throw new AbortException("Findings could not be read; no empty scan result will be published.");
        List<Finding> findings;
        try { findings = CliJson.parseFindings(findExec.stdout); }
        catch (IOException error) { throw new AbortException("Findings document is invalid; no scan result will be published."); }
        for (Finding finding : findings) if (finding.getCampaignId() != null && !campaignId.equals(finding.getCampaignId())) throw new AbortException("A finding belongs to a different campaign.");

        if (recordIssues) {
            try {
                String sarif = new SarifWriter().toSarif(findings, mode);
                out.child("darkmoon.sarif").write(sarif, "UTF-8");
                listener.getLogger().println("[darkmoon] SARIF written: " + sarifPattern()
                        + " (" + findings.size() + " result(s)). Publish it with: "
                        + "recordIssues(enabledForFailure: true, tools: [sarif(pattern: '"
                        + sarifPattern() + "')]).");
            } catch (RuntimeException e) {
                throw new AbortException("Could not generate the requested SARIF artifact.");
            }
        }

        // Gate and displayed counts use the fetched findings, never stale totals.
        SeveritySummary summary = fromFindings(findings);

        // ---- 4) reports ----
        if (archiveReport) {
            try {
                DarkmoonCliRunner.Exec report = runner.report(campaignId, out.child("darkmoon-report.md"), false);
                if (report.exitCode != 0) { out.child("darkmoon-report.md").delete(); listener.getLogger().println("[darkmoon] Redacted report is unavailable."); }
            } catch (IOException error) {
                listener.getLogger().println("[darkmoon] Redacted report is unavailable.");
            }
            if (includeFullReport) {
                try {
                    DarkmoonCliRunner.Exec report = runner.report(campaignId, out.child("darkmoon-report-full.md"), true);
                    if (report.exitCode != 0) { out.child("darkmoon-report-full.md").delete(); listener.getLogger().println("[darkmoon] Full report is unavailable."); }
                    else listener.getLogger().println("[darkmoon] Full report fetched under the explicit artifact opt-in.");
                } catch (IOException error) {
                    listener.getLogger().println("[darkmoon] Full report is unavailable.");
                }
            }
        }

        // ---- 5) redaction-safe console summary ----
        printSummary(listener, campaignId, summary, findings.size());

        // ---- 6) archive machine outputs + report (internal, access-controlled) ----
        if (archiveReport) {
            archive(run, workspace, env, launcher, listener);
        }

        // ---- 7) fail policy from the severity summary ----
        applyFailPolicy(run, listener, summary);
    }

    /** CSV of severities the CLI should treat as failing, derived from {@link #failOn}. */
    private String failOnCsv() {
        Severity t = parseThreshold(failOn);
        if (t == null) {
            return "none";
        }
        StringJoiner sj = new StringJoiner(",");
        for (Severity s : Severity.values()) {
            if (s.isAtLeast(t)) {
                sj.add(s.id());
            }
        }
        return sj.toString();
    }

    private static SeveritySummary fromFindings(List<Finding> findings) {
        SeveritySummary s = new SeveritySummary();
        for (Finding f : findings) {
            switch (f.getSeverity()) {
                case CRITICAL:
                    s.setCritical(s.getCritical() + 1);
                    break;
                case HIGH:
                    s.setHigh(s.getHigh() + 1);
                    break;
                case MEDIUM:
                    s.setMedium(s.getMedium() + 1);
                    break;
                case LOW:
                    s.setLow(s.getLow() + 1);
                    break;
                case INFO:
                default:
                    s.setInfo(s.getInfo() + 1);
                    break;
            }
        }
        s.setTotal(findings.size());
        return s;
    }

    private void printSummary(TaskListener l, String campaignId, SeveritySummary s, int findingCount) {
        StringBuilder sb = new StringBuilder();
        sb.append("\n[darkmoon] ===== Scan summary =====\n");
        sb.append("[darkmoon] campaign: ").append(campaignId).append('\n');
        sb.append("[darkmoon] findings: ").append(findingCount)
                .append("  (critical=").append(s.getCritical())
                .append(", high=").append(s.getHigh())
                .append(", medium=").append(s.getMedium())
                .append(", low=").append(s.getLow())
                .append(", info=").append(s.getInfo()).append(")\n");
        sb.append("[darkmoon] Artifact visibility follows this Jenkins job's permissions.\n");
        sb.append("[darkmoon] =========================");
        l.getLogger().println(sb.toString());
    }

    private void applyFailPolicy(Run<?, ?> run, TaskListener l, SeveritySummary s) {
        Severity failThreshold = parseThreshold(failOn);
        Severity unstableThreshold = parseThreshold(unstableOn);

        if (failThreshold != null && s.countAtLeast(failThreshold) > 0) {
            int n = s.countAtLeast(failThreshold);
            l.getLogger().println("[darkmoon] FAIL: " + n + " finding(s) at or above '"
                    + failThreshold.id() + "' -> marking build FAILURE.");
            run.setResult(Result.FAILURE);
            return;
        }
        if (unstableThreshold != null && s.countAtLeast(unstableThreshold) > 0) {
            int n = s.countAtLeast(unstableThreshold);
            l.getLogger().println("[darkmoon] UNSTABLE: " + n + " finding(s) at or above '"
                    + unstableThreshold.id() + "' -> marking build UNSTABLE.");
            run.setResult(Result.UNSTABLE);
            return;
        }
        l.getLogger().println("[darkmoon] Fail policy not triggered (failOn='" + failOn
                + "', unstableOn='" + unstableOn + "').");
    }

    /** {@code null} means "never" (none/empty). */
    @CheckForNull
    private static Severity parseThreshold(String value) {
        if (value == null) {
            return null;
        }
        String v = value.trim().toLowerCase();
        if (v.isEmpty() || v.equals("none") || v.equals("never")) {
            return null;
        }
        return Severity.fromString(v);
    }

    /** Best-effort archive used on failure paths so the internal CLI log stays retrievable. */
    private void archiveQuietly(
            Run<?, ?> run, FilePath workspace, EnvVars env, Launcher launcher, TaskListener listener) {
        try {
            archive(run, workspace, env, launcher, listener);
        } catch (Exception ignored) {
            // never mask the primary failure
        }
    }

    private void archive(Run<?, ?> run, FilePath workspace, EnvVars env, Launcher launcher, TaskListener listener)
            throws InterruptedException, IOException {
        String directory = env.expand(outputDir).replace('\\', '/');
        String includes = String.join(",", List.of(directory + "/darkmoon.sarif", directory + "/darkmoon-report.md", directory + "/darkmoon-report-full.md", directory + "/" + DarkmoonCliRunner.LOG_FILE));
        ArtifactArchiver archiver = new ArtifactArchiver(includes);
        archiver.setAllowEmptyArchive(true);
        archiver.setFollowSymlinks(false);
        archiver.setOnlyIfSuccessful(false);
        archiver.perform(run, workspace, env, launcher, listener);
    }

    @CheckForNull
    private String resolveSecret(
            Run<?, ?> run, String id, String apiUrlForDomain, TaskListener listener, String label) throws AbortException {
        if (id == null || id.isBlank()) {
            return null;
        }
        StringCredentials creds = CredentialsProvider.findCredentialById(
                id,
                StringCredentials.class,
                run,
                URIRequirementBuilder.fromUri(apiUrlForDomain == null ? "" : apiUrlForDomain).build());
        if (creds == null) {
            throw new AbortException("Configured " + label + " credential is unavailable or is not Secret Text.");
        }
        CredentialsProvider.track(run, creds);
        return creds.getSecret().getPlainText();
    }

    @Symbol("darkmoonScan")
    @Extension
    public static final class DescriptorImpl extends BuildStepDescriptor<Builder> {

        @Override
        public boolean isApplicable(Class<? extends AbstractProject> jobType) {
            return true;
        }

        @NonNull
        @Override
        public String getDisplayName() {
            return "Darkmoon security scan";
        }

        public ListBoxModel doFillModeItems() {
            ListBoxModel m = new ListBoxModel();
            m.add("Auto-detect (OSS or Pro)", "auto");
            m.add("OSS (CLI)", "oss");
            m.add("Pro (REST API)", "pro");
            return m;
        }

        public ListBoxModel doFillFailOnItems() {
            return severityItems();
        }

        public ListBoxModel doFillUnstableOnItems() {
            return severityItems();
        }

        private ListBoxModel severityItems() {
            ListBoxModel m = new ListBoxModel();
            m.add("Never", "none");
            m.add("Critical", "critical");
            m.add("High", "high");
            m.add("Medium", "medium");
            m.add("Low", "low");
            m.add("Info", "info");
            return m;
        }

        public FormValidation doCheckTarget(@QueryParameter String value) {
            if (value == null || value.isBlank()) {
                return FormValidation.error("A target (URL or host) is required.");
            }
            return FormValidation.ok();
        }

        public ListBoxModel doFillCredentialsIdItems(
                @AncestorInPath Item item,
                @QueryParameter String credentialsId,
                @QueryParameter String apiUrl) {
            return credentialItems(item, credentialsId, apiUrl);
        }

        public ListBoxModel doFillLicenseCredentialsIdItems(
                @AncestorInPath Item item,
                @QueryParameter String licenseCredentialsId,
                @QueryParameter String apiUrl) {
            return credentialItems(item, licenseCredentialsId, apiUrl);
        }

        private ListBoxModel credentialItems(Item item, String current, String apiUrl) {
            StandardListBoxModel model = new StandardListBoxModel();
            if (item == null) {
                if (!Jenkins.get().hasPermission(Jenkins.ADMINISTER)) {
                    return model.includeCurrentValue(current);
                }
            } else {
                if (!item.hasPermission(Item.EXTENDED_READ)
                        && !item.hasPermission(CredentialsProvider.USE_ITEM)) {
                    return model.includeCurrentValue(current);
                }
            }
            return model.includeEmptyValue()
                    .includeMatchingAs(
                            item instanceof Queue.Task
                                    ? ((Queue.Task) item).getDefaultAuthentication2()
                                    : ACL.SYSTEM2,
                            item,
                            StringCredentials.class,
                            URIRequirementBuilder.fromUri(apiUrl == null ? "" : apiUrl).build(),
                            CredentialsMatchers.always())
                    .includeCurrentValue(current);
        }
    }
}
