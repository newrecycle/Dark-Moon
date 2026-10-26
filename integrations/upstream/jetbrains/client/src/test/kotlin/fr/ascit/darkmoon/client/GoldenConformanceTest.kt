package fr.ascit.darkmoon.client

import kotlinx.serialization.Serializable
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Validates the Kotlin wire model against the LANGUAGE-NEUTRAL conformance
 * goldens shipped by the foundation (the conformance `.golden.json` files). These
 * goldens are the canonical normalized contract output that OSS, Pro and this
 * Kotlin port must all agree on. Deserializing them into the frozen Kotlin types
 * proves the port is field-complete and correctly typed for the frozen contract.
 */
class GoldenConformanceTest {

    @Serializable
    private data class Golden(
        val contractVersion: String,
        val campaign: Campaign,
        val severitySummary: SeveritySummary,
        val findings: List<Finding>,
    )

    private fun load(name: String): Golden {
        val text = javaClass.getResource("/fixtures/conformance/$name")!!.readText()
        return DarkmoonJson.decodeFromString(Golden.serializer(), text)
    }

    private val goldens = listOf(
        "camp_20260924_70602bf9.golden.json",
        "camp_20260728_9018be77.golden.json",
    )

    @Test fun goldensPinContractVersion() {
        goldens.forEach { assertEquals(CONTRACT_VERSION, load(it).contractVersion) }
    }

    @Test fun campaignSeverityMatchesSummary() {
        goldens.forEach {
            val g = load(it)
            assertEquals(g.severitySummary, g.campaign.severity)
            assertEquals(
                g.severitySummary.critical + g.severitySummary.high + g.severitySummary.medium +
                    g.severitySummary.low + g.severitySummary.info,
                g.severitySummary.total,
            )
        }
    }

    @Test fun findingsUseCanonicalEnumsAndAreRedactionSafe() {
        goldens.forEach { name ->
            val g = load(name)
            assertTrue("golden must have findings", g.findings.isNotEmpty())
            g.findings.forEach { f ->
                // Enum membership is guaranteed by successful deserialization into the
                // frozen enums; evidence must be absent in the default surface.
                assertNull("golden findings are redaction-safe (evidence == null)", f.evidence)
                assertTrue(f.severity in Severity.entries)
                assertTrue(f.status in FindingStatus.entries)
            }
        }
    }

    @Test fun specificGoldenValuesRoundTrip() {
        val g = load("camp_20260924_70602bf9.golden.json")
        assertEquals("camp_20260924_70602bf9", g.campaign.id)
        assertEquals("127.0.0.1:3000", g.campaign.target)
        assertEquals(CampaignStatus.COMPLETED, g.campaign.status)
        assertEquals(OverallRisk.CRITICAL, g.campaign.overallRisk)
        assertEquals(900L, g.campaign.durationSeconds)
        assertEquals(5, g.findings.size)
        assertEquals(2, g.severitySummary.critical)
        // A critical, exploited SQLi finding is present and fully typed.
        val sqli = g.findings.first { it.severity == Severity.CRITICAL }
        assertEquals(FindingStatus.EXPLOITED, sqli.status)
        assertTrue((sqli.cvssScore ?: 0.0) >= 9.0)
    }
}
