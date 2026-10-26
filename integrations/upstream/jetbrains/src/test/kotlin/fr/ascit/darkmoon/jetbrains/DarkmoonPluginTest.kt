package fr.ascit.darkmoon.jetbrains

import com.intellij.openapi.application.ApplicationManager
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import fr.ascit.darkmoon.client.Campaign
import fr.ascit.darkmoon.client.CampaignRef
import fr.ascit.darkmoon.client.Capabilities
import fr.ascit.darkmoon.client.CapabilityGate
import fr.ascit.darkmoon.client.CliConfig
import fr.ascit.darkmoon.client.CliDarkmoonClient
import fr.ascit.darkmoon.client.DetectedBy
import fr.ascit.darkmoon.client.FindingReadOptions
import fr.ascit.darkmoon.client.ReportOptions
import fr.ascit.darkmoon.client.Edition
import fr.ascit.darkmoon.client.Features
import fr.ascit.darkmoon.client.Finding
import fr.ascit.darkmoon.client.FindingStatus
import fr.ascit.darkmoon.client.Severity
import fr.ascit.darkmoon.jetbrains.notifications.StarCta
import fr.ascit.darkmoon.jetbrains.services.DarkmoonProjectService
import fr.ascit.darkmoon.jetbrains.settings.DarkmoonSettings
import fr.ascit.darkmoon.jetbrains.toolwindow.VulnerabilitiesTableModel
import fr.ascit.darkmoon.client.ClientMode
import java.io.File
import java.util.concurrent.TimeUnit

class DarkmoonPluginTest : BasePlatformTestCase() {

    private fun <T> offEdt(block: () -> T): T =
        ApplicationManager.getApplication().executeOnPooledThread<T> { block() }
            .get(60, TimeUnit.SECONDS)

    private fun nodeAvailable(): Boolean = try {
        ProcessBuilder("node", "--version").start().waitFor(10, TimeUnit.SECONDS)
    } catch (e: Exception) { false }

    private fun stubCommand(): String? {
        val stub = System.getProperty("darkmoon.stub") ?: return null
        return if (File(stub).exists()) "node $stub" else null
    }

    // ---- settings ----------------------------------------------------------

    fun testSettingsPersistenceAndTokens() {
        val s = DarkmoonSettings.getInstance()
        s.mode = ClientMode.PRO
        s.baseUrl = "https://darkmoon.example.com"
        s.cliCommand = "node /opt/darkmoon/cli.cjs"
        assertEquals(ClientMode.PRO, s.mode)
        assertEquals("https://darkmoon.example.com", s.baseUrl)
        assertEquals(listOf("node", "/opt/darkmoon/cli.cjs"), s.commandTokens())
        // reset for other tests
        s.mode = ClientMode.AUTO
        s.baseUrl = ""
        s.cliCommand = "darkmoon-ci"
        assertEquals(listOf("darkmoon-ci"), s.commandTokens())
    }

    // ---- star CTA (growth guardrails) --------------------------------------

    fun testStarCtaShownFlagDefaultsFalse() {
        val state = DarkmoonSettings.State()
        assertFalse("flag must default to not-yet-shown", state.starCtaShown)
        assertTrue("growth CTA must default to enabled", state.growthCtaEnabled)
    }

    fun testStarCtaShowsOnFirstRealResult() {
        val state = DarkmoonSettings.State()
        assertTrue(
            "first non-empty result with a fresh, enabled state must be eligible",
            StarCta.shouldShowStarCta(state, findingsCount = 3, envDisabled = false),
        )
    }

    fun testStarCtaNeverShowsOnEmptyFindings() {
        val state = DarkmoonSettings.State()
        assertFalse(
            "empty findings must never trigger the CTA",
            StarCta.shouldShowStarCta(state, findingsCount = 0, envDisabled = false),
        )
    }

    fun testStarCtaIsOnceOnly() {
        val state = DarkmoonSettings.State()
        // First eligibility passes; caller then flips the flag as the real path does.
        assertTrue(StarCta.shouldShowStarCta(state, findingsCount = 5, envDisabled = false))
        state.starCtaShown = true
        assertFalse(
            "a second real result must not re-show the CTA",
            StarCta.shouldShowStarCta(state, findingsCount = 5, envDisabled = false),
        )
    }

    fun testStarCtaRespectsSettingOptOut() {
        val state = DarkmoonSettings.State(growthCtaEnabled = false)
        assertFalse(
            "disabling the growth CTA setting must suppress it",
            StarCta.shouldShowStarCta(state, findingsCount = 4, envDisabled = false),
        )
    }

    fun testStarCtaRespectsEnvOptOut() {
        val state = DarkmoonSettings.State()
        assertFalse(
            "the env opt-out must suppress even an otherwise-eligible CTA",
            StarCta.shouldShowStarCta(state, findingsCount = 4, envDisabled = true),
        )
    }

    // ---- table model -------------------------------------------------------

    fun testVulnTableModelColumns() {
        val model = VulnerabilitiesTableModel()
        val f = Finding(
            id = "n1", campaignId = "camp_1", title = "SQLi login",
            severity = Severity.CRITICAL, status = FindingStatus.EXPLOITED,
            category = "sql_injection", endpoint = "/rest/user/login", edition = Edition.OSS,
        )
        model.setFindings(listOf(f))
        assertEquals(1, model.rowCount)
        assertEquals(Severity.CRITICAL, model.getValueAt(0, 0))
        assertEquals("SQLi login", model.getValueAt(0, 1))
        assertEquals("/rest/user/login", model.getValueAt(0, 2))
        assertEquals("exploited", model.getValueAt(0, 3))
        assertEquals("camp_1", model.getValueAt(0, 4))
        assertSame(f, model.findingAt(0))
    }

    fun testSeverityComparatorOrdersMostSevereFirst() {
        val list = listOf(Severity.LOW, Severity.CRITICAL, Severity.MEDIUM, Severity.INFO, Severity.HIGH)
        val sorted = list.sortedWith(VulnerabilitiesTableModel.SEVERITY_COMPARATOR)
        assertEquals(
            listOf(Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO),
            sorted,
        )
    }

    // ---- capability gating -------------------------------------------------

    fun testCapabilityGateDegradesOnOss() {
        val oss = Capabilities(
            edition = Edition.OSS, mode = Edition.OSS, version = "x", available = true,
            features = Features(), detectedBy = DetectedBy.SYSTEM_INFO,
        )
        assertTrue(CapabilityGate.canLaunchCampaign(oss))
        assertFalse(CapabilityGate.canRemediate(oss))
        assertFalse(CapabilityGate.canStreamProgress(oss))
        val pro = oss.copy(
            edition = Edition.PRO, mode = Edition.PRO,
            features = Features(restApi = true, streaming = true, remediation = true, scheduler = true),
        )
        assertTrue(CapabilityGate.canRemediate(pro))
        assertTrue(CapabilityGate.canStreamProgress(pro))
    }

    // ---- service integration over the darkmoon-ci test double --------------

    fun testOssRefreshViaService() {
        val cmd = stubCommand() ?: return
        if (!nodeAvailable()) return
        val s = DarkmoonSettings.getInstance()
        s.mode = ClientMode.OSS
        s.cliCommand = cmd
        try {
            val service = DarkmoonProjectService.getInstance(project)
            val caps = offEdt { service.refresh() }
            assertEquals(Edition.OSS, caps.edition)
            assertTrue(CapabilityGate.canLaunchCampaign(caps))
            assertFalse(CapabilityGate.canRemediate(caps))
            assertEquals(2, service.campaigns.size)
            val findings = offEdt { service.findings("camp_20260924_70602bf9") }
            assertEquals(5, findings.size)
            assertTrue("service-surfaced findings must be redaction-safe",
                findings.all { it.evidence == null })
        } finally {
            s.mode = ClientMode.AUTO
            s.cliCommand = "darkmoon-ci"
        }
    }

    /**
     * REAL end-to-end: drives CliDarkmoonClient through the shipped bridge, which
     * calls the real @darkmoon/client library against the real OSS data dir. Skips
     * cleanly when the foundation library or the data dir are not present on this
     * machine (so the repo stays portable).
     */
    fun testRealLibraryViaBridge() {
        if (!nodeAvailable()) return
        val lib = File("/home/mehdi/darkmoon-client/dist/index.js")
        val dataDir = File("/home/mehdi/Dark-Moon-prod/darkmoon-settings")
        val bridge = System.getProperty("darkmoon.bridge")?.let { File(it) } ?: return
        if (!lib.exists() || !dataDir.exists() || !bridge.exists()) return

        val client = CliDarkmoonClient(
            CliConfig(
                command = listOf("node", bridge.absolutePath),
                mode = ClientMode.OSS,
                extraEnv = mapOf(
                    "DARKMOON_CLIENT_MODULE" to lib.absolutePath,
                    "DARKMOON_OSS_DATA_DIR" to dataDir.absolutePath,
                    "DARKMOON_OSS_REPORTS_DIR" to File(dataDir.parentFile, "reports").absolutePath,
                ),
                timeoutMs = 60_000,
            )
        )

        val caps = offEdt { client.detect() }
        assertEquals(Edition.OSS, caps.edition)
        assertTrue(caps.available)
        assertFalse(CapabilityGate.canRemediate(caps))

        val camps: List<Campaign> = offEdt { client.listCampaigns() }
        assertTrue("real data dir should expose multiple campaigns", camps.size >= 2)
        val known = camps.firstOrNull { it.id == "camp_20260924_70602bf9" }
        assertNotNull("known campaign must be present in real data", known)

        val findings = offEdt { client.listFindings(fr.ascit.darkmoon.client.FindingFilter(campaignId = "camp_20260924_70602bf9")) }
        assertEquals(5, findings.size)
        assertTrue("list surface must be redaction-safe", findings.all { it.evidence == null })

        val withEv = offEdt { client.getFinding(findings.first().id, FindingReadOptions(includeEvidence = true)) }
        assertNotNull(withEv.evidence)
        assertTrue("evidence must be redacted by default", withEv.evidence!!.redacted)

        // Report is data-dependent; keep it exception-safe (a thrown error on a
        // pooled thread would be logged and fail the test) and assert only if ready.
        val report = offEdt { runCatching { client.getReport(CampaignRef.of("camp_20260924_70602bf9"), ReportOptions()) }.getOrNull() }
        if (report != null && report.ready) {
            assertTrue("default report must be redacted", report.redacted)
            val full = offEdt { runCatching { client.getReport(CampaignRef.of("camp_20260924_70602bf9"), ReportOptions(full = true, private = true)) }.getOrNull() }
            if (full != null) {
                assertFalse(full.redacted)
                assertTrue("full report should be at least as complete as the redacted one",
                    full.content.length >= report.content.length)
            }
        }
    }

    fun testProGatingViaService() {
        val cmd = stubCommand() ?: return
        if (!nodeAvailable()) return
        val s = DarkmoonSettings.getInstance()
        s.mode = ClientMode.PRO
        s.cliCommand = cmd
        try {
            val service = DarkmoonProjectService.getInstance(project)
            val caps = offEdt { service.refresh() }
            assertEquals(Edition.PRO, caps.edition)
            assertTrue(CapabilityGate.canRemediate(caps))
            assertTrue(caps.warnings.any { it.contains("must_change_password") })
        } finally {
            s.mode = ClientMode.AUTO
            s.cliCommand = "darkmoon-ci"
        }
    }
}
