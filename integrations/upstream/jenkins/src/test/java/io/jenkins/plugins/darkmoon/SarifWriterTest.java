package io.jenkins.plugins.darkmoon;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.jenkins.plugins.darkmoon.contract.CliJson;
import io.jenkins.plugins.darkmoon.contract.Finding;
import io.jenkins.plugins.darkmoon.sarif.SarifWriter;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.junit.jupiter.api.Test;

class SarifWriterTest {

    private static String findingsJson() throws IOException {
        try (InputStream in = SarifWriterTest.class.getResourceAsStream("/fixtures/findings.json")) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    @Test
    void mapsFindingsToSarif() throws IOException {
        List<Finding> findings = CliJson.parseFindings(findingsJson());
        String sarif = new SarifWriter().toSarif(findings, "oss");

        ObjectMapper m = new ObjectMapper();
        JsonNode root = m.readTree(sarif);
        assertEquals("2.1.0", root.get("version").asText());
        JsonNode run = root.get("runs").get(0);
        assertEquals("Darkmoon", run.get("tool").get("driver").get("name").asText());

        JsonNode results = run.get("results");
        assertEquals(5, results.size());

        // critical -> error, high -> error, medium -> warning
        JsonNode first = results.get(0);
        assertEquals("error", first.get("level").asText());
        assertTrue(first.get("ruleId").asText().startsWith("darkmoon/"));
        assertTrue(first.get("message").get("text").asText().contains("SQL Injection"));

        boolean sawWarning = false;
        for (JsonNode r : results) {
            if ("warning".equals(r.get("level").asText())) {
                sawWarning = true;
            }
        }
        assertTrue(sawWarning, "medium findings should map to SARIF level 'warning'");
    }

    @Test
    void sarifNeverLeaksEvidence() throws IOException {
        List<Finding> findings = CliJson.parseFindings(findingsJson());
        String sarif = new SarifWriter().toSarif(findings, "oss");
        // Redaction-safe: no raw evidence blocks / secret material from the internal
        // format may appear. (Words like "Bearer token" in a finding's description
        // are redaction-safe prose, not evidence, and are intentionally allowed.)
        assertFalse(sarif.contains("raw_response"));
        assertFalse(sarif.contains("raw_request"));
        assertFalse(sarif.contains("\"evidence\""));
        assertFalse(sarif.contains("eyJ")); // no JWT token fragments
    }

    @Test
    void emptyFindingsProduceValidSarif() {
        String sarif = new SarifWriter().toSarif(List.of(), "oss");
        assertTrue(sarif.contains("\"results\""));
    }
}
