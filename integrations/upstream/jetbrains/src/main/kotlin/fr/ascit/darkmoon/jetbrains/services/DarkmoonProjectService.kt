package fr.ascit.darkmoon.jetbrains.services

import com.intellij.openapi.components.Service
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
import java.util.concurrent.atomic.AtomicLong

/**
 * Per-project holder of the Darkmoon client and cached, redaction-safe data.
 * Every method here is blocking and MUST be invoked from a background thread
 * (the tool window uses Task.Backgroundable / pooled threads). The Pro token is
 * supplied lazily from PasswordSafe and only reaches the CLI via an environment
 * variable, never argv or logs.
 */
@Service(Service.Level.PROJECT)
class DarkmoonProjectService(private val project: Project) {

    private val generation = AtomicLong()
    val revision: Long get() = generation.get()

    @Volatile var capabilities: Capabilities? = null
        private set

    @Volatile var campaigns: List<Campaign> = emptyList()
        private set

    fun connectionStamp(): List<Any> {
        val settings = DarkmoonSettings.getInstance()
        return listOf(revision, DarkmoonSecretService.getInstance().revision, settings.mode.wire,
            settings.baseUrl, settings.cliCommand, settings.workingDir, settings.ossDataDir, settings.ossReportsDir)
    }

    /** Builds a fresh client from current settings + secret. Never caches secrets. */
    fun client(): DarkmoonClient {
        val origin = connectionStamp()
        val settings = DarkmoonSettings.getInstance()
        val workingDir = settings.workingDir.takeIf { it.isNotBlank() }?.let { File(it) }
        val bundled = settings.cliCommand.isBlank() || settings.cliCommand in listOf("bundled", "darkmoon-ci")
        val environment = mutableMapOf<String, String>()
        if (bundled) environment["DARKMOON_CLIENT_MODULE"] = BundledBridge.module()
        if (settings.ossDataDir.isNotBlank()) environment["DARKMOON_OSS_DATA_DIR"] = settings.ossDataDir
        if (settings.ossReportsDir.isNotBlank()) environment["DARKMOON_OSS_REPORTS_DIR"] = settings.ossReportsDir
        return CliDarkmoonClient(
            CliConfig(
                command = if (bundled) BundledBridge.command() else settings.commandTokens(),
                extraEnv = environment,
                mode = settings.mode,
                baseUrl = settings.baseUrl.takeIf { it.isNotBlank() },
                workingDir = workingDir,
                tokenProvider = {
                    check(connectionStamp() == origin) { "Connection changed before credential access" }
                    val token = DarkmoonSecretService.getInstance().getToken()
                    check(connectionStamp() == origin) { "Connection changed during credential access" }
                    token
                },
            )
        )
    }

    /** Detect + list campaigns. Blocking; call off-EDT. */
    fun refresh(): Capabilities {
        val revision = synchronized(this) {
            capabilities = null
            campaigns = emptyList()
            generation.incrementAndGet()
        }
        val origin = connectionStamp()
        val c = client()
        val caps = c.detect()
        val records = c.listCampaigns()
        synchronized(this) {
            if (generation.get() != revision || connectionStamp() != origin) throw IllegalStateException("A newer connection refresh replaced this request")
            campaigns = records
            capabilities = caps
        }
        return caps
    }

    /** Redaction-safe findings for a campaign (evidence == null). Blocking. */
    fun findings(campaignId: String): List<Finding> =
        client().listFindings(FindingFilter(campaignId = campaignId))

    /** A single finding with (redacted, or full when the two-key opt-in is passed) evidence. */
    fun findingWithEvidence(id: String, full: Boolean, expected: List<Any>? = null): Finding {
        val origin = expected ?: connectionStamp()
        check(connectionStamp() == origin) { "Connection changed before reading evidence" }
        val reader = client()
        check(connectionStamp() == origin) { "Connection changed before reading evidence" }
        return reader.getFinding(id, FindingReadOptions(includeEvidence = true, full = full, private = full))
    }

    /** A report. Full body only with the explicit two-key opt-in. Blocking. */
    fun report(campaignId: String, full: Boolean, expected: List<Any>? = null): Report {
        val origin = expected ?: connectionStamp()
        check(connectionStamp() == origin) { "Connection changed before reading the report" }
        val reader = client()
        check(connectionStamp() == origin) { "Connection changed before reading the report" }
        return reader.getReport(CampaignRef.of(campaignId), ReportOptions(full = full, private = full))
    }

    fun launch(input: LaunchInput): LaunchResult = client().launchCampaign(input)

    companion object {
        fun getInstance(project: Project): DarkmoonProjectService =
            project.getService(DarkmoonProjectService::class.java)
    }
}
