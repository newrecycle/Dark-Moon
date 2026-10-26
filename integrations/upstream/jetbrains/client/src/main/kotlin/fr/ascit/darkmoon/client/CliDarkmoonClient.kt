package fr.ascit.darkmoon.client

import kotlinx.serialization.builtins.ListSerializer
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
    private val runner: ProcessRunner = DefaultProcessRunner(),
) : DarkmoonClient {

    private fun baseEnv(): Map<String, String> {
        val env = HashMap<String, String>(config.extraEnv)
        config.tokenProvider?.invoke()?.let { if (it.isNotBlank()) env["DARKMOON_TOKEN"] = it }
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
            val err = res.stderr.trim().take(2000).ifEmpty { res.stdout.trim().take(500) }
            throw DarkmoonClientException("darkmoon-ci ${args.firstOrNull()} failed (exit ${res.exitCode}): $err")
        }
        return res.stdout
    }

    private inline fun <reified T> decode(json: String): T =
        try {
            DarkmoonJson.decodeFromString<T>(json.trim())
        } catch (e: Exception) {
            throw DarkmoonClientException("Malformed darkmoon-ci output: ${e.message}", e)
        }

    private fun idOf(ref: CampaignRef): String = when (ref) {
        is CampaignRef.Id -> ref.id
        is CampaignRef.Handle -> ref.handle.campaignId
            ?: ref.handle.runId
            ?: throw DarkmoonClientException("Correlation handle has no resolvable campaign/run id yet")
        is CampaignRef.Launch -> ref.result.campaignId
            ?: ref.result.runId
            ?: ref.result.correlation.campaignId
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

    override fun getCampaign(ref: CampaignRef): Campaign =
        decode(exec(listOf("campaign", "get", idOf(ref))))

    override fun getCampaignStatus(ref: CampaignRef): Campaign {
        val args = mutableListOf("campaign", "status", idOf(ref))
        correlationJson(ref)?.let { args += listOf("--correlation", it) }
        return decode(exec(args))
    }

    override fun listCampaigns(filter: CampaignFilter): List<Campaign> {
        val args = mutableListOf("campaigns", "list")
        filter.status?.let { args += listOf("--status", it) }
        filter.targetId?.let { args += listOf("--target-id", it) }
        return DarkmoonJson.decodeFromString(ListSerializer(Campaign.serializer()), exec(args).trim())
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
        return DarkmoonJson.decodeFromString(ListSerializer(Finding.serializer()), exec(args).trim())
    }

    override fun getFinding(id: String, opts: FindingReadOptions): Finding {
        val args = mutableListOf("finding", "get", id)
        applyEvidenceFlags(args, opts)
        return decode(exec(args))
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
        decode(exec(listOf("summary", idOf(ref))))

    override fun getReport(ref: CampaignRef, opts: ReportOptions): Report {
        if (opts.full && !opts.private) {
            throw RedactionPolicyException(
                "Full (un-redacted) report requires full=true AND private=true (two-key opt-in)."
            )
        }
        val args = mutableListOf("report", idOf(ref))
        if (opts.full) { args += "--full"; args += "--private" }
        return decode(exec(args))
    }

    override fun waitForCompletion(ref: CampaignRef, opts: WaitOptions): Campaign {
        val deadline = System.currentTimeMillis() + opts.timeoutMs
        var last: Campaign? = null
        var resolvedRef = ref
        while (System.currentTimeMillis() < deadline) {
            val c = getCampaignStatus(resolvedRef)
            if (last?.status != c.status) opts.onProgress?.invoke(c)
            last = c
            // Once we learn the campaign id, pin to it for cheaper subsequent polls.
            if (resolvedRef !is CampaignRef.Id) resolvedRef = CampaignRef.Id(c.id)
            if (c.status.isTerminal) return c
            Thread.sleep(opts.pollIntervalMs.coerceAtLeast(250))
        }
        val stuck = last
        if (stuck != null && !opts.failOnStuck) return stuck
        throw DarkmoonClientException(
            "Campaign did not reach a terminal state within ${opts.timeoutMs}ms" +
                (last?.let { " (last status: ${it.status.wire})" } ?: "")
        )
    }

    override fun streamProgress(ref: CampaignRef): Sequence<ProgressEvent> {
        val args = config.command + listOf("stream", idOf(ref)) + globalFlags()
        return runner.stream(args, baseEnv(), config.workingDir).mapNotNull { line ->
            runCatching { DarkmoonJson.decodeFromString<ProgressEvent>(line) }.getOrNull()
        }
    }
}
