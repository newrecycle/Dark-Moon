/*
 * darkmoon-client-kotlin — Kotlin port of the FROZEN @darkmoon/client contract
 * (§2.2 of the integrations plan). These types MIRROR src/contract.ts one-to-one.
 *
 * The runtime backend is NOT reimplemented here: detection, normalization and
 * redaction live once, in the TypeScript client / `darkmoon-ci` CLI, which this
 * module drives as a subprocess (see CliDarkmoonClient). These classes are the
 * wire model of the CLI's `--json` output and the shapes the JetBrains plugin
 * builds its UI against.
 *
 * DO NOT change field names or enum value sets without bumping CONTRACT_VERSION
 * (and the shared conformance fixtures).
 */
package fr.ascit.darkmoon.client

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** Contract version. The plugin pins against the major. Mirrors contract.ts. */
const val CONTRACT_VERSION: String = "1.0.0"

/** Canonical, lowercase severity set. Everything normalizes into this. */
@Serializable
enum class Severity {
    @SerialName("critical") CRITICAL,
    @SerialName("high") HIGH,
    @SerialName("medium") MEDIUM,
    @SerialName("low") LOW,
    @SerialName("info") INFO;

    /** Descending order weight; higher = more severe. Used for table sorting. */
    val weight: Int get() = when (this) {
        CRITICAL -> 5; HIGH -> 4; MEDIUM -> 3; LOW -> 2; INFO -> 1
    }

    val wire: String get() = name.lowercase()
}

/** Campaign overall risk: a severity, or "none". */
@Serializable
enum class OverallRisk {
    @SerialName("critical") CRITICAL,
    @SerialName("high") HIGH,
    @SerialName("medium") MEDIUM,
    @SerialName("low") LOW,
    @SerialName("info") INFO,
    @SerialName("none") NONE;

    val wire: String get() = name.lowercase()
}

/** Canonical finding status set. */
@Serializable
enum class FindingStatus {
    @SerialName("exploited") EXPLOITED,
    @SerialName("confirmed") CONFIRMED,
    @SerialName("unconfirmed") UNCONFIRMED,
    @SerialName("remediated") REMEDIATED;

    val wire: String get() = name.lowercase()
}

/** Canonical campaign lifecycle status. */
@Serializable
enum class CampaignStatus {
    @SerialName("queued") QUEUED,
    @SerialName("running") RUNNING,
    @SerialName("completed") COMPLETED,
    @SerialName("stopped") STOPPED,
    @SerialName("failed") FAILED,
    @SerialName("unknown") UNKNOWN;

    val wire: String get() = name.lowercase()

    val isTerminal: Boolean get() = this == COMPLETED || this == STOPPED || this == FAILED
}

/** Which Darkmoon backend served a call. */
@Serializable
enum class Edition {
    @SerialName("oss") OSS,
    @SerialName("pro") PRO;

    val wire: String get() = name.lowercase()
}

/** Backend selection override. */
@Serializable
enum class ClientMode {
    @SerialName("auto") AUTO,
    @SerialName("oss") OSS,
    @SerialName("pro") PRO;

    val wire: String get() = name.lowercase()
}

/**
 * Additive, normalized capability map. The plugin gates Pro-only UI on these
 * flags rather than sniffing the edition directly (§2.4 degradation).
 */
@Serializable
data class Features(
    val restApi: Boolean = false,
    val streaming: Boolean = false,
    val auth: Boolean = false,
    val remediation: Boolean = false,
    val dashboard: Boolean = false,
    val scheduler: Boolean = false,
)

@Serializable
enum class DetectedBy {
    @SerialName("system-info") SYSTEM_INFO,
    @SerialName("root-probe") ROOT_PROBE,
    @SerialName("cli-probe") CLI_PROBE,
    @SerialName("override") OVERRIDE,
    @SerialName("config") CONFIG,
}

/** Result of detect(). Never contains secrets. */
@Serializable
data class Capabilities(
    val edition: Edition,
    val mode: Edition,
    val version: String,
    val available: Boolean,
    val features: Features = Features(),
    val detectedBy: DetectedBy,
    val warnings: List<String> = emptyList(),
)

/** Aggregated severity counts — the redaction-safe default surface. */
@Serializable
data class SeveritySummary(
    val critical: Int = 0,
    val high: Int = 0,
    val medium: Int = 0,
    val low: Int = 0,
    val info: Int = 0,
    val total: Int = 0,
)

/** A normalized campaign. `raw` is intentionally omitted from this wire model. */
@Serializable
data class Campaign(
    val id: String,
    val projectId: String? = null,
    val targetId: String? = null,
    val sessionId: String? = null,
    val target: String? = null,
    val status: CampaignStatus,
    val overallRisk: OverallRisk = OverallRisk.NONE,
    val createdAt: String? = null,
    val durationSeconds: Long? = null,
    val reportPath: String? = null,
    val isSubagent: Boolean = false,
    val severity: SeveritySummary = SeveritySummary(),
    val executiveSummary: String? = null,
    /**
     * The serving edition. The CLI always emits it; it defaults to OSS only so
     * the edition-agnostic conformance goldens (which omit it) deserialize.
     */
    val edition: Edition = Edition.OSS,
)

/** Evidence attached to a finding. Redacted unless explicitly opted in. */
@Serializable
data class FindingEvidence(
    val commands: List<String> = emptyList(),
    val payloads: List<String> = emptyList(),
    val rawRequest: String? = null,
    val rawResponse: String? = null,
    val extractedData: String? = null,
    val logs: List<String> = emptyList(),
    val explanation: String? = null,
    /** True when this evidence object has been passed through the redactor. */
    val redacted: Boolean = true,
)

/** A normalized finding / vulnerability. */
@Serializable
data class Finding(
    val id: String,
    val campaignId: String? = null,
    val projectId: String? = null,
    val targetId: String? = null,
    val title: String? = null,
    val severity: Severity,
    val status: FindingStatus,
    val category: String? = null,
    val cve: String? = null,
    val cvssScore: Double? = null,
    val cvssVector: String? = null,
    val mitreAttackId: String? = null,
    val mitreAttackName: String? = null,
    val endpoint: String? = null,
    val description: String? = null,
    val remediation: String? = null,
    val discoveredByAgent: String? = null,
    val discoveredAt: String? = null,
    /** Redaction-safe by default; only present when includeEvidence was set. */
    val evidence: FindingEvidence? = null,
    /** Serving edition; defaults to OSS only so edition-agnostic goldens deserialize. */
    val edition: Edition = Edition.OSS,
)

/**
 * A campaign report. `ready` distinguishes a real report from a Pro
 * placeholder-200. `redacted` is true unless the two-key full opt-in was used.
 */
@Serializable
data class Report(
    val campaignId: String,
    val format: String = "markdown",
    val content: String,
    val ready: Boolean,
    val redacted: Boolean,
)

/** Live progress event surfaced by streamProgress(). */
@Serializable
data class ProgressEvent(
    val type: String,
    val campaignId: String? = null,
    val runId: String? = null,
    val message: String? = null,
    val terminal: Boolean = false,
)

/** Input to launchCampaign(). Mirrors the Pro CampaignRunRequest + OSS flags. */
@Serializable
data class LaunchInput(
    val target: String,
    val program: String? = null,
    val targets: List<String>? = null,
    val outOfScope: List<String>? = null,
    val exclude: List<String>? = null,
    val focus: List<String>? = null,
    val credentials: List<String>? = null,
    val tokens: List<String>? = null,
    val noise: String? = null,
    val severity: String? = null,
    val format: String? = null,
    val rules: List<String>? = null,
    val safeHarbor: String? = null,
    // Pro remediation phase (opt-in). credentialId is an opaque ref, never a secret.
    val remediate: Boolean? = null,
    val gitRepo: String? = null,
    val credentialId: String? = null,
    val createRepo: Boolean? = null,
)

/** Opaque correlation handle returned by launchCampaign(). Treat as a token. */
@Serializable
data class CorrelationHandle(
    val edition: Edition,
    val runId: String? = null,
    val campaignId: String? = null,
    val nonce: String? = null,
    val preCampaignIds: List<String>? = null,
    val startedAtMs: Long = 0,
)

/** Result of launchCampaign(). */
@Serializable
data class LaunchResult(
    val correlation: CorrelationHandle,
    val campaignId: String? = null,
    val runId: String? = null,
)

/** Filters for listCampaigns. */
data class CampaignFilter(
    val targetId: String? = null,
    val status: String? = null,
)

/** Filters for listFindings. */
data class FindingFilter(
    val campaignId: String? = null,
    val projectId: String? = null,
    val targetId: String? = null,
    val severity: String? = null,
    val category: String? = null,
    val status: String? = null,
)

/**
 * Options for getReport(). The full, UN-redacted body carries rehydrated real
 * values; it is a deliberate two-key opt-in and must never reach CI output.
 */
data class ReportOptions(
    val full: Boolean = false,
    val private: Boolean = false,
)

/** Options for finding/evidence exposure. Evidence is null unless included. */
data class FindingReadOptions(
    val includeEvidence: Boolean = false,
    val full: Boolean = false,
    val private: Boolean = false,
)

/** Options for waitForCompletion(). */
data class WaitOptions(
    val timeoutMs: Long = 30 * 60 * 1000,
    val pollIntervalMs: Long = 5000,
    val failOnStuck: Boolean = true,
    val onProgress: ((Campaign) -> Unit)? = null,
)
