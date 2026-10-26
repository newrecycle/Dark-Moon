package fr.ascit.darkmoon.client

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File

/**
 * Conformance: drives the Kotlin CliDarkmoonClient against the `darkmoon-ci`
 * test double over a REAL subprocess boundary, using the SAME raw fixtures the
 * TypeScript client's conformance suite consumes. Validates the frozen contract:
 * normalization, enum canonicalization, capability gating and redaction.
 */
class ConformanceTest {

    private val fixturesDir: File = run {
        val url = javaClass.getResource("/fixtures") ?: error("fixtures resource missing")
        File(url.toURI())
    }
    private val stub: File = run {
        val url = javaClass.getResource("/stub/darkmoon-ci.mjs") ?: error("stub resource missing")
        File(url.toURI())
    }

    private fun client(mode: ClientMode): CliDarkmoonClient = CliDarkmoonClient(
        CliConfig(
            command = listOf("node", stub.absolutePath),
            mode = mode,
            extraEnv = mapOf("DARKMOON_FIXTURES" to fixturesDir.absolutePath),
            timeoutMs = 30_000,
        )
    )

    // ---- detection & capability gating (§2.4) ------------------------------

    @Test fun contractVersionPinned() = assertEquals("1.0.0", CONTRACT_VERSION)

    @Test fun detectOss() {
        val caps = client(ClientMode.OSS).detect()
        assertEquals(Edition.OSS, caps.edition)
        assertTrue(caps.available)
        assertFalse("OSS must not advertise REST API", caps.features.restApi)
        assertFalse("OSS must not advertise remediation", caps.features.remediation)
        assertFalse(CapabilityGate.canRemediate(caps))
        assertFalse(CapabilityGate.canStreamProgress(caps))
        assertTrue(CapabilityGate.canLaunchCampaign(caps))
        assertTrue(caps.warnings.isEmpty())
    }

    @Test fun detectProAdvertisesFeaturesAndSurfacesWarnings() {
        val caps = client(ClientMode.PRO).detect()
        assertEquals(Edition.PRO, caps.edition)
        assertTrue(caps.features.restApi)
        assertTrue(caps.features.remediation)
        assertTrue(CapabilityGate.canRemediate(caps))
        assertTrue(CapabilityGate.canStreamProgress(caps))
        assertTrue(CapabilityGate.canSchedule(caps))
        assertTrue("Pro default-password warning must be surfaced",
            caps.warnings.any { it.contains("must_change_password") })
    }

    // ---- campaign normalization --------------------------------------------

    @Test fun listCampaignsOssNormalizes() {
        val camps = client(ClientMode.OSS).listCampaigns()
        assertEquals(2, camps.size)
        val c = camps.first { it.id == "camp_20260924_70602bf9" }
        assertEquals("proj_ae3ed3", c.projectId)
        assertEquals("tgt_be6f57", c.targetId)
        assertEquals("70602bf9", c.sessionId)
        assertEquals(CampaignStatus.COMPLETED, c.status)
        assertEquals(OverallRisk.CRITICAL, c.overallRisk)
        assertEquals(900L, c.durationSeconds)
        assertFalse(c.isSubagent)
        assertEquals(Edition.OSS, c.edition)
        assertEquals(5, c.severity.total)
        assertEquals(2, c.severity.critical)
        assertNotNull(c.executiveSummary)
    }

    @Test fun campaignFilterByStatus() {
        val camps = client(ClientMode.OSS).listCampaigns(CampaignFilter(status = "completed"))
        assertTrue(camps.isNotEmpty())
        assertTrue(camps.all { it.status == CampaignStatus.COMPLETED })
    }

    @Test fun getSeveritySummary() {
        val s = client(ClientMode.OSS).getSeveritySummary(CampaignRef.of("camp_20260924_70602bf9"))
        assertEquals(5, s.total)
        assertEquals(1, s.high)
        assertEquals(2, s.medium)
    }

    // ---- findings normalization + redaction (§4) ---------------------------

    @Test fun listFindingsRedactsEvidenceByDefault() {
        val findings = client(ClientMode.OSS)
            .listFindings(FindingFilter(campaignId = "camp_20260924_70602bf9"))
        assertEquals(5, findings.size)
        assertTrue(findings.all { it.evidence == null })
        val crit = findings.first { it.severity == Severity.CRITICAL }
        assertEquals(FindingStatus.EXPLOITED, crit.status)
        assertNotNull(crit.description)
        assertNotNull(crit.remediation)
    }

    @Test fun getFindingIncludeEvidenceIsRedacted() {
        val cli = client(ClientMode.OSS)
        val first = cli.listFindings(FindingFilter(campaignId = "camp_20260924_70602bf9")).first()
        val f = cli.getFinding(first.id, FindingReadOptions(includeEvidence = true))
        assertNotNull("evidence must be present when includeEvidence=true", f.evidence)
        val ev = f.evidence!!
        assertTrue("redacted flag must be true", ev.redacted)
        val body = (ev.rawResponse ?: "") + (ev.rawRequest ?: "") + ev.logs.joinToString()
        assertFalse("redacted evidence must not leak a raw JWT", body.contains("eyJ0eXA"))
    }

    @Test fun getFindingFullRequiresTwoKeyOptIn() {
        val cli = client(ClientMode.OSS)
        val first = cli.listFindings(FindingFilter(campaignId = "camp_20260924_70602bf9")).first()
        try {
            cli.getFinding(first.id, FindingReadOptions(includeEvidence = true, full = true, private = false))
            fail("must reject full evidence without the private key")
        } catch (e: RedactionPolicyException) { /* expected */ }
    }

    @Test fun getFindingFullOptInReturnsUnredacted() {
        val cli = client(ClientMode.OSS)
        val findings = cli.listFindings(FindingFilter(campaignId = "camp_20260924_70602bf9"))
        // pick the finding whose raw evidence carries the admin JWT
        val target = findings.first { it.title?.contains("login", ignoreCase = true) == true }
        val f = cli.getFinding(target.id, FindingReadOptions(includeEvidence = true, full = true, private = true))
        val ev = f.evidence!!
        assertFalse(ev.redacted)
        assertTrue("full evidence must rehydrate the real token",
            (ev.rawResponse ?: "").contains("eyJ0eXA"))
    }

    // ---- reports (§4 redaction-safe) ---------------------------------------

    @Test fun reportRedactedByDefault() {
        val r = client(ClientMode.OSS).getReport(CampaignRef.of("camp_20260924_70602bf9"))
        assertTrue(r.ready)
        assertTrue(r.redacted)
        assertFalse("default report must not leak the raw target host", r.content.contains("127.0.0.1:3000"))
        assertTrue(r.content.contains("REDACTED"))
    }

    @Test fun reportFullRequiresPrivate() {
        try {
            client(ClientMode.OSS).getReport(CampaignRef.of("camp_20260924_70602bf9"),
                ReportOptions(full = true, private = false))
            fail("must reject full report without private key")
        } catch (e: RedactionPolicyException) { /* expected */ }
    }

    @Test fun reportFullOptInRehydrates() {
        val r = client(ClientMode.OSS).getReport(CampaignRef.of("camp_20260924_70602bf9"),
            ReportOptions(full = true, private = true))
        assertFalse(r.redacted)
        assertTrue(r.content.contains("127.0.0.1:3000"))
    }

    @Test fun reportMissingIsNotReady() {
        val r = client(ClientMode.OSS).getReport(CampaignRef.of("camp_20260728_9018be77"))
        assertFalse(r.ready)
        assertEquals("", r.content)
    }

    // ---- lifecycle ----------------------------------------------------------

    @Test fun waitForCompletionReturnsTerminal() {
        val c = client(ClientMode.PRO).waitForCompletion(
            CampaignRef.of("camp_pro"), WaitOptions(timeoutMs = 5000, pollIntervalMs = 250))
        assertTrue(c.status.isTerminal)
    }

    @Test fun waitForCompletionFailsOnStuck() {
        try {
            client(ClientMode.PRO).waitForCompletion(
                CampaignRef.of("sub"), WaitOptions(timeoutMs = 800, pollIntervalMs = 250))
            fail("running campaign should time out")
        } catch (e: DarkmoonClientException) { /* expected */ }
    }

    @Test fun streamProgressEmitsTerminal() {
        val events = client(ClientMode.PRO).streamProgress(CampaignRef.of("camp_pro")).toList()
        assertTrue(events.isNotEmpty())
        assertTrue(events.last().terminal)
    }

    @Test fun launchReturnsCorrelationHandle() {
        val res = client(ClientMode.PRO).launchCampaign(LaunchInput(target = "http://127.0.0.1:3000"))
        assertEquals(Edition.PRO, res.correlation.edition)
        assertNotNull(res.correlation.startedAtMs)
        assertNull(res.campaignId)
    }
}
