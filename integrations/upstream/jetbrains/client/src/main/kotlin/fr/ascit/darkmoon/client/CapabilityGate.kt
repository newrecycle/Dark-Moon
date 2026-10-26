package fr.ascit.darkmoon.client

/**
 * Central capability gating (§2.4 graceful degradation). The plugin asks these
 * questions instead of checking `edition == PRO` directly, so a future OSS build
 * that gains a feature lights up automatically and a Pro build that lacks one
 * stays disabled.
 */
object CapabilityGate {

    fun isPro(caps: Capabilities?): Boolean = caps?.edition == Edition.PRO

    /** Launching a campaign requires a reachable backend. */
    fun canLaunchCampaign(caps: Capabilities?): Boolean = caps?.available == true

    /** Live SSE progress streaming — Pro only. */
    fun canStreamProgress(caps: Capabilities?): Boolean = caps?.features?.streaming == true

    /** Remediation → pull-request phase — Pro only. Deliberately UI-gated, never auto-run. */
    fun canRemediate(caps: Capabilities?): Boolean = caps?.features?.remediation == true

    /** Scheduled campaigns — Pro only. */
    fun canSchedule(caps: Capabilities?): Boolean = caps?.features?.scheduler == true

    /** A hosted web dashboard exists (Pro). Used only to offer an "open in browser" hint. */
    fun hasDashboard(caps: Capabilities?): Boolean = caps?.features?.dashboard == true

    /** Human-readable, secret-free reason a Pro-only action is unavailable. */
    fun proOnlyReason(feature: String): String =
        "$feature is a Darkmoon Pro feature and is disabled on this OSS backend."
}
