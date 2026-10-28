package fr.ascit.darkmoon.client

import kotlinx.serialization.encodeToString
import java.io.File

/**
 * Configuration for driving the `darkmoon-ci` CLI (the shipped TypeScript
 * `@darkmoon/client`). Non-secret settings travel on argv; the Pro JWT travels
 * only via the DARKMOON_TOKEN environment variable so it never appears in a
 * process listing or a captured command line (§4 threat model).
 */
data class CliConfig(
    /** Base command, e.g. listOf("darkmoon-ci") or listOf("node", "/path/darkmoon-ci.cjs"). */
    val command: List<String>,
    val mode: ClientMode = ClientMode.AUTO,
    val baseUrl: String? = null,
    val workingDir: File? = null,
    val extraEnv: Map<String, String> = emptyMap(),
    /** Supplies the Pro JWT on demand; returns null in OSS mode. Never logged. */
    val tokenProvider: (() -> String?)? = null,
    val timeoutMs: Long = 60_000,
)

/**
 * The single runtime backend for the JetBrains plugin. It does NOT reimplement
 * detection, normalization or redaction — those live once in the TypeScript
 * client. This adapter builds argv, runs the CLI, and deserializes the frozen
 * contract JSON. It additionally enforces the redaction two-key opt-in
 * client-side as defence in depth.
 *
 * ## `darkmoon-ci` CLI contract expected by this adapter
 * Every call receives the global flags `--json` and `--mode <mode>` (plus
 * `--base-url <url>` when configured). Subcommands:
 * ```
 *   detect
 *   campaigns list        [--status S] [--target-id T]
 *   campaign  get    <id>
 *   campaign  status <id> [--correlation <json>]
 *   findings  list        [--campaign C] [--project P] [--target-id T]
 *                         [--severity S] [--category K] [--status S]
 *                         [--include-evidence] [--full --private]
 *   finding   get    <id> [--include-evidence] [--full --private]
 *   summary   <campaignId>
 *   report    <campaignId> [--full --private]
 *   launch                (LaunchInput JSON on stdin)
 *   stream    <id>        (NDJSON ProgressEvent lines on stdout)
 * ```
 * The contract JSON *shapes* are frozen (§2.2); these subcommand spellings are
 * an integration detail localized to this class and documented for alignment
 * with the shipped CLI.
 */
class CliDarkmoonClient(
    private val config: CliConfig,
    private val runner: ProcessRunner = DefaultProcessRunner(config.timeoutMs),
) : DarkmoonClient {

    private fun baseEnv(): Map<String, String> {
        val env = HashMap<String, String>(config.extraEnv)
        if (config.tokenProvider != null) env["DARKMOON_TOKEN"] = config.tokenProvider.invoke().orEmpty()
        return env
    }

    private fun globalFlags(): List<String> = buildList {
        add("--json")
        add("--mode"); add(config.mode.wire)
        config.baseUrl?.takeIf { it.isNotBlank() }?.let { add("--base-url"); add(it) }
    }

    private fun exec(args: List<String>, stdin: String? = null): String {
        val argv = config.command + args + globalFlags()
        val res = runner.run(argv, baseEnv(), config.workingDir, stdin, config.timeoutMs)
        if (res.exitCode != 0) {
            throw DarkmoonClientException("darkmoon-ci ${args.firstOrNull()} failed (exit ${res.exitCode}); assessment result is unavailable")
        }
        return res.stdout
    }

    private inline fun <reified T> decode(json: String): T =
        try {
            DarkmoonJson.decodeFromString<T>(json.trim())
        } catch (e: Exception) {
            throw DarkmoonClientException("Malformed darkmoon-ci output; response contents are withheld")
        }

    private fun idOf(ref: CampaignRef): String = when (ref) {
        is CampaignRef.Id -> ref.id
        is CampaignRef.Handle -> ref.handle.campaignId
            ?: ref.handle.runId
            ?: throw DarkmoonClientException("Correlation handle has no resolvable campaign/run id yet")
        is CampaignRef.Launch -> ref.result.campaignId
            ?: ref.result.correlation.campaignId
            ?: ref.result.runId
            ?: ref.result.correlation.runId
            ?: throw DarkmoonClientException("Launch result has no resolvable campaign/run id yet")
    }

    private fun correlationJson(ref: CampaignRef): String? = when (ref) {
        is CampaignRef.Handle -> if (ref.handle.campaignId == null)
            DarkmoonJson.encodeToString(ref.handle) else null
        is CampaignRef.Launch -> if (ref.result.campaignId == null)
            DarkmoonJson.encodeToString(ref.result.correlation) else null
        else -> null
    }

    override fun detect(): Capabilities = decode(exec(listOf("detect")))

    override fun launchCampaign(input: LaunchInput): LaunchResult {
        val json = DarkmoonJson.encodeToString(input)
        return decode(exec(listOf("launch"), stdin = json))
    }

    private fun referenceArgs(args: List<String>, ref: CampaignRef): List<String> =
        correlationJson(ref)?.let { args + listOf("--correlation", it) } ?: args

    private fun expectedCampaignId(ref: CampaignRef): String? = when (ref) {
        is CampaignRef.Id -> ref.id
        is CampaignRef.Handle -> ref.handle.campaignId
        is CampaignRef.Launch -> ref.result.campaignId ?: ref.result.correlation.campaignId
    }

    private fun checkedCampaign(ref: CampaignRef, campaign: Campaign): Campaign {
        val expected = expectedCampaignId(ref)
        if (expected != null && campaign.id != expected) throw DarkmoonClientException("Campaign identity does not match the request")
        return campaign
    }

    override fun getCampaign(ref: CampaignRef): Campaign =
        checkedCampaign(ref, decode(exec(referenceArgs(listOf("campaign", "get", idOf(ref)), ref))))

    override fun getCampaignStatus(ref: CampaignRef): Campaign {
        val args = mutableListOf("campaign", "status", idOf(ref))
        correlationJson(ref)?.let { args += listOf("--correlation", it) }
        return checkedCampaign(ref, decode(exec(args)))
    }

    override fun listCampaigns(filter: CampaignFilter): List<Campaign> {
        val args = mutableListOf("campaigns", "list")
        filter.status?.let { args += listOf("--status", it) }
        filter.targetId?.let { args += listOf("--target-id", it) }
        return decode(exec(args))
    }

    override fun listFindings(filter: FindingFilter, opts: FindingReadOptions): List<Finding> {
        val args = mutableListOf("findings", "list")
        filter.campaignId?.let { args += listOf("--campaign", it) }
        filter.projectId?.let { args += listOf("--project", it) }
        filter.targetId?.let { args += listOf("--target-id", it) }
        filter.severity?.let { args += listOf("--severity", it) }
        filter.category?.let { args += listOf("--category", it) }
        filter.status?.let { args += listOf("--status", it) }
        applyEvidenceFlags(args, opts)
        return decode(exec(args))
    }

    override fun getFinding(id: String, opts: FindingReadOptions): Finding {
        val args = mutableListOf("finding", "get", id)
        applyEvidenceFlags(args, opts)
        val finding: Finding = decode(exec(args))
        if (finding.id != id) throw DarkmoonClientException("Finding identity does not match the request")
        return finding
    }

    private fun applyEvidenceFlags(args: MutableList<String>, opts: FindingReadOptions) {
        if (opts.full && !(opts.includeEvidence && opts.private)) {
            throw RedactionPolicyException(
                "Full (un-redacted) evidence requires includeEvidence=true AND private=true (two-key opt-in)."
            )
        }
        if (opts.includeEvidence) args += "--include-evidence"
        if (opts.full) { args += "--full"; args += "--private" }
    }

    override fun getSeveritySummary(ref: CampaignRef): SeveritySummary =
        decode(exec(referenceArgs(listOf("summary", idOf(ref)), ref)))

    override fun getReport(ref: CampaignRef, opts: ReportOptions): Report {
        if (opts.full && !opts.private) {
            throw RedactionPolicyException(
                "Full (un-redacted) report requires full=true AND private=true (two-key opt-in)."
            )
        }
        val args = mutableListOf("report", idOf(ref))
        if (opts.full) { args += "--full"; args += "--private" }
        val report: Report = decode(exec(referenceArgs(args, ref)))
        val expected = expectedCampaignId(ref)
        if (expected != null && report.campaignId != expected) throw DarkmoonClientException("Report identity does not match the request")
        return report
    }

    override fun waitForCompletion(ref: CampaignRef, opts: WaitOptions): Campaign {
        if (opts.timeoutMs <= 0 || opts.pollIntervalMs <= 0) throw DarkmoonClientException("Timeout and polling interval must be positive")
        val started = System.nanoTime()
        var last: Campaign? = null
        var resolvedRef = ref
        while ((System.nanoTime() - started) / 1_000_000 < opts.timeoutMs) {
            val c = getCampaignStatus(resolvedRef)
            if (last?.status != c.status) opts.onProgress?.invoke(c)
            last = c
            // Once we learn the campaign id, pin to it for cheaper subsequent polls.
            if (resolvedRef !is CampaignRef.Id && c.id.isNotBlank() && !c.id.startsWith("run:")) resolvedRef = CampaignRef.Id(c.id)
            if (c.status.isTerminal) return c
            val remaining = opts.timeoutMs - (System.nanoTime() - started) / 1_000_000
            if (remaining > 0) Thread.sleep(minOf(opts.pollIntervalMs.coerceAtLeast(1), remaining))
        }
        val stuck = last
        if (stuck != null && !opts.failOnStuck) return stuck
        throw DarkmoonClientException(
            "Campaign did not reach a terminal state within ${opts.timeoutMs}ms" +
                (last?.let { " (last status: ${it.status.wire})" } ?: "")
        )
    }

    override fun streamProgress(ref: CampaignRef): Sequence<ProgressEvent> = sequence {
        val correlation = when (ref) {
            is CampaignRef.Handle -> DarkmoonJson.encodeToString(ref.handle)
            is CampaignRef.Launch -> DarkmoonJson.encodeToString(ref.result.correlation)
            else -> null
        }
        val args = config.command + listOf("stream", idOf(ref)) +
            (correlation?.let { listOf("--correlation", it) } ?: emptyList()) + globalFlags()
        var terminal = false
        for (line in runner.stream(args, baseEnv(), config.workingDir)) {
            val event: ProgressEvent = decode(line)
            val expected = expectedCampaignId(ref)
            if (expected != null && event.campaignId != null && event.campaignId != expected) throw DarkmoonClientException("Progress campaign identity does not match the request")
            if (terminal) throw DarkmoonClientException("Progress stream emitted data after terminal completion")
            yield(event)
            terminal = event.terminal
        }
        if (!terminal) throw DarkmoonClientException("Progress stream closed before terminal completion")
    }
}
