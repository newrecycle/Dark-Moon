package fr.ascit.darkmoon.jetbrains.services

import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.thisLogger
import com.intellij.openapi.project.Project
import fr.ascit.darkmoon.client.Campaign
import fr.ascit.darkmoon.client.CampaignRef
import fr.ascit.darkmoon.client.Capabilities
import fr.ascit.darkmoon.client.CliConfig
import fr.ascit.darkmoon.client.CliDarkmoonClient
import fr.ascit.darkmoon.client.DarkmoonClient
import fr.ascit.darkmoon.client.Finding
import fr.ascit.darkmoon.client.FindingFilter
import fr.ascit.darkmoon.client.FindingReadOptions
import fr.ascit.darkmoon.client.LaunchInput
import fr.ascit.darkmoon.client.LaunchResult
import fr.ascit.darkmoon.client.Report
import fr.ascit.darkmoon.client.ReportOptions
import fr.ascit.darkmoon.jetbrains.settings.DarkmoonSecretService
import fr.ascit.darkmoon.jetbrains.settings.DarkmoonSettings
import java.io.File

/**
 * Per-project holder of the Darkmoon client and cached, redaction-safe data.
 * Every method here is blocking and MUST be invoked from a background thread
 * (the tool window uses Task.Backgroundable / pooled threads). The Pro token is
 * supplied lazily from PasswordSafe and only reaches the CLI via an environment
 * variable, never argv or logs.
 */
@Service(Service.Level.PROJECT)
class DarkmoonProjectService(private val project: Project) {

    @Volatile var capabilities: Capabilities? = null
        private set

    @Volatile var campaigns: List<Campaign> = emptyList()
        private set

    /** Builds a fresh client from current settings + secret. Never caches secrets. */
    fun client(): DarkmoonClient {
        val settings = DarkmoonSettings.getInstance()
        val workingDir = settings.workingDir.takeIf { it.isNotBlank() }?.let { File(it) }
        return CliDarkmoonClient(
            CliConfig(
                command = settings.commandTokens(),
                mode = settings.mode,
                baseUrl = settings.baseUrl.takeIf { it.isNotBlank() },
                workingDir = workingDir,
                tokenProvider = { DarkmoonSecretService.getInstance().getToken() },
            )
        )
    }

    /** Detect + list campaigns. Blocking; call off-EDT. */
    fun refresh(): Capabilities {
        val c = client()
        val caps = c.detect()
        capabilities = caps
        campaigns = runCatching { c.listCampaigns() }
            .onFailure { thisLogger().warn("listCampaigns failed", it) }
            .getOrDefault(emptyList())
        return caps
    }

    /** Redaction-safe findings for a campaign (evidence == null). Blocking. */
    fun findings(campaignId: String): List<Finding> =
        client().listFindings(FindingFilter(campaignId = campaignId))

    /** A single finding with (redacted, or full when the two-key opt-in is passed) evidence. */
    fun findingWithEvidence(id: String, full: Boolean): Finding =
        client().getFinding(id, FindingReadOptions(includeEvidence = true, full = full, private = full))

    /** A report. Full body only with the explicit two-key opt-in. Blocking. */
    fun report(campaignId: String, full: Boolean): Report =
        client().getReport(CampaignRef.of(campaignId), ReportOptions(full = full, private = full))

    fun launch(input: LaunchInput): LaunchResult = client().launchCampaign(input)

    companion object {
        fun getInstance(project: Project): DarkmoonProjectService =
            project.getService(DarkmoonProjectService::class.java)
    }
}
