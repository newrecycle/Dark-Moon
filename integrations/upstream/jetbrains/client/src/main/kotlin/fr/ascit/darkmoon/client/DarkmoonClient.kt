package fr.ascit.darkmoon.client

/**
 * A reference to a campaign: an id string, a correlation handle, or a launch
 * result. Mirrors contract.ts `CampaignRef`.
 */
sealed interface CampaignRef {
    data class Id(val id: String) : CampaignRef
    data class Handle(val handle: CorrelationHandle) : CampaignRef
    data class Launch(val result: LaunchResult) : CampaignRef

    companion object {
        fun of(id: String): CampaignRef = Id(id)
        fun of(handle: CorrelationHandle): CampaignRef = Handle(handle)
        fun of(result: LaunchResult): CampaignRef = Launch(result)
    }
}

/** Thrown when the backend is unreachable or the CLI returns a non-zero result. */
class DarkmoonClientException(message: String, cause: Throwable? = null) :
    RuntimeException(message, cause)

/**
 * Thrown when a caller asks for an UN-redacted / full surface without the
 * required two-key opt-in. Enforced client-side as defence in depth (§4).
 */
class RedactionPolicyException(message: String) : RuntimeException(message)

/**
 * The frozen client surface. Mirrors contract.ts `DarkmoonClientContract`.
 *
 * Methods are blocking and MUST be called off the EDT (from a background thread
 * or a coroutine on Dispatchers.IO). The JetBrains plugin does exactly that.
 */
interface DarkmoonClient {
    fun detect(): Capabilities

    fun launchCampaign(input: LaunchInput): LaunchResult

    fun getCampaignStatus(ref: CampaignRef): Campaign

    fun listCampaigns(filter: CampaignFilter = CampaignFilter()): List<Campaign>

    fun getCampaign(ref: CampaignRef): Campaign

    fun listFindings(
        filter: FindingFilter,
        opts: FindingReadOptions = FindingReadOptions(),
    ): List<Finding>

    fun getFinding(id: String, opts: FindingReadOptions = FindingReadOptions()): Finding

    fun getSeveritySummary(ref: CampaignRef): SeveritySummary

    fun getReport(ref: CampaignRef, opts: ReportOptions = ReportOptions()): Report

    fun waitForCompletion(ref: CampaignRef, opts: WaitOptions = WaitOptions()): Campaign

    /** A blocking, lazily-consumed stream of progress events. */
    fun streamProgress(ref: CampaignRef): Sequence<ProgressEvent>
}
