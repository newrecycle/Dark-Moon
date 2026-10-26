package io.jenkins.plugins.darkmoon.sarif;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import edu.umd.cs.findbugs.annotations.NonNull;
import io.jenkins.plugins.darkmoon.contract.Finding;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Maps normalized, redaction-safe {@link Finding}s to a SARIF 2.1.0 document that
 * Warnings Next Generation ({@code recordIssues(tools:[sarif(...)])}) ingests.
 *
 * <p>This is the plugin's finding-to-issue mapping. Only redaction-safe fields are
 * emitted (title, category, severity, CVSS score/vector, MITRE ATT&amp;CK id,
 * endpoint, description, remediation) — never evidence, raw requests/responses or
 * extracted data (§4 threat model). SARIF {@code level} is derived from severity:
 * critical/high -&gt; error, medium -&gt; warning, low/info -&gt; note.
 */
public final class SarifWriter {

    private static final String SARIF_VERSION = "2.1.0";
    private static final String SCHEMA =
            "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json";
    private static final String TOOL_NAME = "Darkmoon";
    private static final String INFO_URI = "https://github.com/jenkinsci/darkmoon-scan-plugin";

    private final ObjectMapper mapper = new ObjectMapper();

    /** Build a pretty-printed SARIF document string from the findings. */
    @NonNull
    public String toSarif(@NonNull List<Finding> findings, @NonNull String toolVersion) {
        ObjectNode root = mapper.createObjectNode();
        root.put("$schema", SCHEMA);
        root.put("version", SARIF_VERSION);

        ArrayNode runs = root.putArray("runs");
        ObjectNode run = runs.addObject();

        // --- tool.driver + rules ---
        ObjectNode tool = run.putObject("tool");
        ObjectNode driver = tool.putObject("driver");
        driver.put("name", TOOL_NAME);
        driver.put("informationUri", INFO_URI);
        driver.put("version", toolVersion == null || toolVersion.isBlank() ? "unknown" : toolVersion);

        Map<String, Finding> ruleIndex = new LinkedHashMap<>();
        for (Finding f : findings) {
            ruleIndex.putIfAbsent(f.ruleId(), f);
        }
        ArrayNode rules = driver.putArray("rules");
        Map<String, Integer> ruleOrder = new LinkedHashMap<>();
        int idx = 0;
        for (Map.Entry<String, Finding> e : ruleIndex.entrySet()) {
            Finding f = e.getValue();
            String category = f.getCategory();
            String mitre = f.getMitreAttackId();
            ObjectNode rule = rules.addObject();
            rule.put("id", e.getKey());
            rule.put("name", safeName(category, e.getKey()));
            rule.putObject("shortDescription").put("text", nonNull(category, e.getKey()));
            rule.putObject("fullDescription").put("text", nonNull(f.getDescription(), nonNull(f.getTitle(), e.getKey())));
            rule.put("helpUri", INFO_URI);
            ObjectNode rprops = rule.putObject("properties");
            ArrayNode tags = rprops.putArray("tags");
            tags.add("security");
            if (category != null) {
                tags.add(category);
            }
            if (mitre != null) {
                rprops.put("mitre-attack", mitre);
            }
            ruleOrder.put(e.getKey(), idx++);
        }

        // --- results ---
        ArrayNode results = run.putArray("results");
        for (Finding f : findings) {
            ObjectNode res = results.addObject();
            res.put("ruleId", f.ruleId());
            Integer ri = ruleOrder.get(f.ruleId());
            if (ri != null) {
                res.put("ruleIndex", ri.intValue());
            }
            res.put("level", f.getSeverity().sarifLevel());
            res.putObject("message").put("text", buildMessage(f));

            // Location: security findings have no source file, so use a logical
            // location (the endpoint / component) plus a synthetic artifact uri so
            // warnings-ng always has something to group on.
            ArrayNode locations = res.putArray("locations");
            ObjectNode loc = locations.addObject();
            String where = nonNull(f.getEndpoint(), nonNull(f.getCategory(), "darkmoon"));
            ObjectNode physical = loc.putObject("physicalLocation");
            physical.putObject("artifactLocation").put("uri", toUri(where));
            physical.putObject("region").put("startLine", 1);
            ArrayNode logical = loc.putArray("logicalLocations");
            logical.addObject().put("fullyQualifiedName", where);

            ObjectNode props = res.putObject("properties");
            props.put("severity", f.getSeverity().id());
            Double cvss = f.getCvssScore();
            if (cvss != null) {
                // GitHub/OSSF convention consumed by several dashboards.
                props.put("security-severity", String.valueOf(cvss));
                props.put("cvssScore", cvss.doubleValue());
            }
            String cvssVector = f.getCvssVector();
            if (cvssVector != null) {
                props.put("cvssVector", cvssVector);
            }
            String mitreId = f.getMitreAttackId();
            if (mitreId != null) {
                props.put("mitreAttackId", mitreId);
            }
            String status = f.getStatus();
            if (status != null) {
                props.put("status", status);
            }
            String agent = f.getDiscoveredByAgent();
            if (agent != null) {
                props.put("agent", agent);
            }
        }

        try {
            return mapper.writerWithDefaultPrettyPrinter().writeValueAsString(root);
        } catch (Exception ex) {
            // Never expose stack/state; SARIF generation must not leak.
            throw new IllegalStateException("Failed to serialize SARIF document");
        }
    }

    private static String buildMessage(Finding f) {
        StringBuilder sb = new StringBuilder();
        sb.append(nonNull(f.getTitle(), nonNull(f.getCategory(), "Finding")));
        Double cvss = f.getCvssScore();
        if (cvss != null) {
            sb.append(" (CVSS ").append(cvss).append(')');
        }
        String rem = f.getRemediation();
        if (rem != null && !rem.isBlank()) {
            sb.append("\nRemediation: ").append(rem.trim());
        }
        return sb.toString();
    }

    private static String toUri(String where) {
        // Turn "GET /api/Users/1" or "POST /rest/user/login" into a stable, uri-ish token.
        String w = where.trim();
        int sp = w.indexOf(' ');
        if (sp > 0 && sp < 8) {
            w = w.substring(sp + 1).trim();
        }
        if (w.isEmpty()) {
            w = "darkmoon";
        }
        return w.startsWith("/") ? "darkmoon:" + w : "darkmoon:/" + w;
    }

    private static String safeName(String primary, String fallback) {
        String base = nonNull(primary, fallback);
        return base.replaceAll("[^A-Za-z0-9_./-]", "_");
    }

    private static String nonNull(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value;
    }
}
