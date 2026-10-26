package io.jenkins.plugins.darkmoon.cli;

import edu.umd.cs.findbugs.annotations.CheckForNull;
import edu.umd.cs.findbugs.annotations.NonNull;
import hudson.EnvVars;
import hudson.FilePath;
import hudson.Launcher;
import hudson.Proc;
import hudson.model.TaskListener;
import hudson.util.ArgumentListBuilder;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

/**
 * Invokes the portable {@code darkmoon-ci} CLI (built on {@code @darkmoon/client})
 * on the build node. The plugin owns Jenkins concerns; the CLI owns the OSS/Pro
 * contract.
 *
 * <p>The CLI is command-oriented and prints machine JSON to <b>stdout</b>:
 *
 * <pre>
 *   darkmoon-ci run    --target &lt;t&gt; [backend] --fail-on &lt;csv&gt; --json   -&gt; verdict {campaignId,...}
 *   darkmoon-ci findings &lt;campaignId&gt; [backend] --json                 -&gt; Finding[]
 *   darkmoon-ci summary  &lt;campaignId&gt; [backend] --json                 -&gt; SeveritySummary
 *   darkmoon-ci report   &lt;campaignId&gt; [backend] --out &lt;file&gt; [--full --private]
 *
 *   backend  = --mode auto|oss|pro [--pro-url URL] [--oss-data-dir D] [--oss-reports-dir R] [--oss-script S]
 *   secrets  = environment ONLY (never argv): DARKMOON_PRO_TOKEN, DARKMOON_PRO_URL, DARKMOON_LICENSE
 *   exit     = 0 pass · 2 fail-policy tripped · 1 tool/usage/runtime error
 * </pre>
 */
public class DarkmoonCliRunner {

    public static final int EXIT_OK = 0;
    public static final int EXIT_POLICY = 2;
    public static final int EXIT_ERROR = 1;

    public static final String LOG_FILE = "darkmoon-ci.log";

    private final Launcher launcher;
    private final FilePath workspace;
    private final FilePath outputDir;
    private final TaskListener listener;
    private final Options options;

    public DarkmoonCliRunner(
            @NonNull Launcher launcher,
            @NonNull FilePath workspace,
            @NonNull FilePath outputDir,
            @NonNull TaskListener listener,
            @NonNull Options options) {
        this.launcher = launcher;
        this.workspace = workspace;
        this.outputDir = outputDir;
        this.listener = listener;
        this.options = options;
    }

    public FilePath logFile() {
        return outputDir.child(LOG_FILE);
    }

    /** Result of a single CLI invocation. */
    public static final class Exec {
        public final int exitCode;
        public final String stdout;

        Exec(int exitCode, String stdout) {
            this.exitCode = exitCode;
            this.stdout = stdout;
        }
    }

    /** {@code run --target ... --fail-on <csv> --json}. */
    public Exec run(@NonNull String failOnCsv) throws IOException, InterruptedException {
        List<String> args = base();
        args.add("run");
        args.add("--target");
        args.add(options.target);
        addBackend(args);
        args.add("--fail-on");
        args.add(failOnCsv);
        if (options.timeoutSeconds > 0) {
            args.add("--timeout");
            args.add(Integer.toString(options.timeoutSeconds));
        }
        args.addAll(options.extraArgs);
        args.add("--json");
        return exec(args);
    }

    /** {@code findings <campaignId> --json}. */
    public Exec findings(@NonNull String campaignId) throws IOException, InterruptedException {
        List<String> args = base();
        args.add("findings");
        args.add(campaignId);
        addBackend(args);
        args.add("--json");
        return exec(args);
    }

    /** {@code summary <campaignId> --json}. */
    public Exec summary(@NonNull String campaignId) throws IOException, InterruptedException {
        List<String> args = base();
        args.add("summary");
        args.add(campaignId);
        addBackend(args);
        args.add("--json");
        return exec(args);
    }

    /** {@code report <campaignId> --out <file> [--full --private]}. */
    public Exec report(@NonNull String campaignId, @NonNull FilePath outFile, boolean full)
            throws IOException, InterruptedException {
        List<String> args = base();
        args.add("report");
        args.add(campaignId);
        addBackend(args);
        args.add("--out");
        args.add(relative(outFile));
        if (full) {
            args.add("--full");
            args.add("--private");
        }
        return exec(args);
    }

    private List<String> base() {
        // cliPath may be "darkmoon-ci" or "node /path/darkmoon-ci.cjs".
        List<String> args = new ArrayList<>();
        for (String tok : options.cliPath.trim().split("\\s+")) {
            if (!tok.isBlank()) {
                args.add(tok);
            }
        }
        return args;
    }

    private void addBackend(List<String> args) {
        args.add("--mode");
        args.add(options.mode);
        if (notBlank(options.apiUrl)) {
            args.add("--pro-url");
            args.add(options.apiUrl);
        }
        if (notBlank(options.ossDataDir)) {
            args.add("--oss-data-dir");
            args.add(options.ossDataDir);
        }
        if (notBlank(options.ossReportsDir)) {
            args.add("--oss-reports-dir");
            args.add(options.ossReportsDir);
        }
        if (notBlank(options.ossScript)) {
            args.add("--oss-script");
            args.add(options.ossScript);
        }
    }

    /** In-memory accumulator for the internal CLI log (stderr + stdout), flushed to file each exec. */
    private final StringBuilder logBuffer = new StringBuilder();

    private Exec exec(List<String> args) throws IOException, InterruptedException {
        outputDir.mkdirs();
        ArgumentListBuilder cmd = new ArgumentListBuilder(args.toArray(new String[0]));

        EnvVars env = new EnvVars(options.baseEnv);
        if (notBlank(options.token)) {
            env.put("DARKMOON_PRO_TOKEN", options.token);
        }
        if (notBlank(options.license)) {
            env.put("DARKMOON_LICENSE", options.license);
        }
        if (notBlank(options.apiUrl)) {
            env.put("DARKMOON_PRO_URL", options.apiUrl);
        }

        listener.getLogger().println("[darkmoon] $ " + cmd.toString());

        ByteArrayOutputStream stdout = new ByteArrayOutputStream();
        ByteArrayOutputStream stderr = new ByteArrayOutputStream();
        // stdout -> captured string (machine JSON); stderr -> internal log only.
        Proc proc = launcher.launch()
                .cmds(cmd)
                .envs(env)
                .pwd(workspace)
                .stdout(stdout)
                .stderr(stderr)
                .start();
        int code;
        if (options.timeoutSeconds > 0) {
            code = proc.joinWithTimeout(
                    (long) options.timeoutSeconds + 120L, TimeUnit.SECONDS, listener);
        } else {
            code = proc.join();
        }
        String outStr = stdout.toString(StandardCharsets.UTF_8);
        String errStr = stderr.toString(StandardCharsets.UTF_8);

        // Accumulate an internal, archived record (secret-scrubbed by the CLI itself).
        logBuffer.append("\n$ ").append(cmd.toString()).append(" (exit=").append(code).append(")\n");
        if (!errStr.isEmpty()) {
            logBuffer.append("--- stderr ---\n").append(errStr).append('\n');
        }
        logBuffer.append("--- stdout ---\n").append(outStr).append('\n');
        logFile().write(logBuffer.toString(), "UTF-8");

        return new Exec(code, outStr);
    }

    private String relative(FilePath file) {
        String ws = workspace.getRemote();
        String f = file.getRemote();
        if (f.startsWith(ws)) {
            String rel = f.substring(ws.length());
            while (rel.startsWith("/") || rel.startsWith("\\")) {
                rel = rel.substring(1);
            }
            return rel.isEmpty() ? f : rel;
        }
        return f;
    }

    private static boolean notBlank(String v) {
        return v != null && !v.isBlank();
    }

    /** Immutable configuration for a runner instance. */
    public static final class Options {
        final String cliPath;
        final String target;
        final String mode;
        final String apiUrl;
        final String ossDataDir;
        final String ossReportsDir;
        final String ossScript;
        final int timeoutSeconds;
        final String token;
        final String license;
        final EnvVars baseEnv;
        final List<String> extraArgs;

        private Options(Builder b) {
            this.cliPath = (b.cliPath == null || b.cliPath.isBlank()) ? "darkmoon-ci" : b.cliPath;
            this.target = b.target;
            this.mode = (b.mode == null || b.mode.isBlank()) ? "auto" : b.mode;
            this.apiUrl = b.apiUrl;
            this.ossDataDir = b.ossDataDir;
            this.ossReportsDir = b.ossReportsDir;
            this.ossScript = b.ossScript;
            this.timeoutSeconds = Math.max(0, b.timeoutSeconds);
            this.token = b.token;
            this.license = b.license;
            this.baseEnv = b.baseEnv == null ? new EnvVars() : b.baseEnv;
            this.extraArgs = b.extraArgs == null ? new ArrayList<>() : b.extraArgs;
        }

        public static Builder builder() {
            return new Builder();
        }

        public static final class Builder {
            private String cliPath;
            private String target;
            private String mode;
            private String apiUrl;
            private String ossDataDir;
            private String ossReportsDir;
            private String ossScript;
            private int timeoutSeconds;
            private String token;
            private String license;
            private EnvVars baseEnv;
            private List<String> extraArgs;

            public Builder cliPath(String v) {
                this.cliPath = v;
                return this;
            }

            public Builder target(String v) {
                this.target = v;
                return this;
            }

            public Builder mode(String v) {
                this.mode = v;
                return this;
            }

            public Builder apiUrl(String v) {
                this.apiUrl = v;
                return this;
            }

            public Builder ossDataDir(String v) {
                this.ossDataDir = v;
                return this;
            }

            public Builder ossReportsDir(String v) {
                this.ossReportsDir = v;
                return this;
            }

            public Builder ossScript(String v) {
                this.ossScript = v;
                return this;
            }

            public Builder timeoutSeconds(int v) {
                this.timeoutSeconds = v;
                return this;
            }

            public Builder token(String v) {
                this.token = v;
                return this;
            }

            public Builder license(String v) {
                this.license = v;
                return this;
            }

            public Builder baseEnv(EnvVars v) {
                this.baseEnv = v;
                return this;
            }

            public Builder extraArgs(List<String> v) {
                this.extraArgs = v;
                return this;
            }

            @NonNull
            public Options build() {
                return new Options(this);
            }
        }
    }
}
