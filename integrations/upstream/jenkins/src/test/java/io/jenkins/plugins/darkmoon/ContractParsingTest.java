package io.jenkins.plugins.darkmoon;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.jenkins.plugins.darkmoon.contract.CliJson;
import io.jenkins.plugins.darkmoon.contract.Finding;
import io.jenkins.plugins.darkmoon.contract.Severity;
import io.jenkins.plugins.darkmoon.contract.SeveritySummary;
import io.jenkins.plugins.darkmoon.contract.Verdict;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.junit.jupiter.api.Test;

/** Parses the REAL normalized output captured from {@code darkmoon-ci} (fixtures/). */
class ContractParsingTest {

    private static String res(String name) throws IOException {
        try (InputStream in = ContractParsingTest.class.getResourceAsStream("/fixtures/" + name)) {
            if (in == null) {
                throw new IOException("missing fixture " + name);
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    @Test
    void parsesRealFindings() throws IOException {
        List<Finding> findings = CliJson.parseFindings(res("findings.json"));
        assertEquals(5, findings.size());
        Finding first = findings.get(0);
        assertEquals(Severity.CRITICAL, first.getSeverity());
        assertEquals("sql_injection", first.getCategory());
        assertEquals("POST /rest/user/login", first.getEndpoint());
        assertEquals(9.8, first.getCvssScore(), 0.0001);
        // Redaction-safe contract: evidence is not modelled / never present.
        assertTrue(first.getTitle().contains("SQL Injection"));
    }

    @Test
    void parsesRealSummary() throws IOException {
        SeveritySummary s = CliJson.parseSummary(res("summary.json"));
        assertEquals(2, s.getCritical());
        assertEquals(1, s.getHigh());
        assertEquals(2, s.getMedium());
        assertEquals(0, s.getLow());
        assertEquals(5, s.getTotal());
        assertEquals(3, s.countAtLeast(Severity.HIGH));
        assertEquals(2, s.countAtLeast(Severity.CRITICAL));
        assertEquals(5, s.countAtLeast(Severity.INFO));
    }

    @Test
    void parsesVerdict() throws IOException {
        Verdict v = CliJson.parseVerdict(
                "{\"campaignId\":\"camp_x\",\"verdict\":\"fail\",\"failOn\":[\"critical\",\"high\"],"
                        + "\"offending\":{},\"total\":5,\"reason\":\"boom\"}");
        assertEquals("camp_x", v.getCampaignId());
        assertTrue(v.failed());
        assertEquals(5, v.getTotal());
    }

    @Test
    void severityOrderingAndUnknown() {
        assertTrue(Severity.CRITICAL.isAtLeast(Severity.HIGH));
        assertFalse(Severity.LOW.isAtLeast(Severity.HIGH));
        assertEquals(Severity.INFO, Severity.fromString("banana"));
        assertEquals(Severity.INFO, Severity.fromString(null));
        assertEquals(Severity.MEDIUM, Severity.fromString("MEDIUM"));
    }
}
