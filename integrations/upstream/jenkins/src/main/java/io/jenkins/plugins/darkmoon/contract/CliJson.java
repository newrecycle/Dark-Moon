package io.jenkins.plugins.darkmoon.contract;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import edu.umd.cs.findbugs.annotations.NonNull;
import java.io.IOException;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Strict CLI documents. Malformed input never becomes a clean empty result. */
public final class CliJson {
    private CliJson() {}
    private static ObjectMapper mapper() {
        return new ObjectMapper().configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false)
                .configure(DeserializationFeature.FAIL_ON_TRAILING_TOKENS, true);
    }
    private static JsonNode document(String json) throws IOException {
        try {
            JsonNode result = mapper().readTree(json);
            if (result == null || result.isNull()) throw new IOException();
            return result;
        } catch (IOException | RuntimeException error) {
            throw new IOException("Invalid CLI JSON document; response contents are withheld");
        }
    }
    private static void require(boolean condition) throws IOException {
        if (!condition) throw new IOException("CLI document is missing required typed fields");
    }
    private static boolean text(JsonNode value) { return value != null && value.isTextual() && !value.asText().isBlank(); }
    @NonNull public static Verdict parseVerdict(@NonNull String json) throws IOException {
        JsonNode value = document(json);
        require(value.isObject() && text(value.get("campaignId")) && value.get("campaignId").asText().matches("[A-Za-z0-9_-]{1,200}"));
        require(text(value.get("verdict")) && Set.of("pass", "fail").contains(value.get("verdict").asText()));
        require(value.path("total").isIntegralNumber() && value.path("total").canConvertToInt() && value.path("total").asInt() >= 0);
        return mapper().treeToValue(value, Verdict.class);
    }
    @NonNull public static List<Finding> parseFindings(@NonNull String json) throws IOException {
        JsonNode values = document(json);
        require(values.isArray());
        Set<String> identities = new HashSet<>();
        for (JsonNode value : values) {
            require(value.isObject() && text(value.get("id")) && identities.add(value.get("id").asText()));
            require(text(value.get("severity")) && Set.of("critical", "high", "medium", "low", "info").contains(value.get("severity").asText()));
            JsonNode score = value.get("cvssScore");
            require(score == null || score.isNull() || score.isNumber() && Double.isFinite(score.asDouble()) && score.asDouble() >= 0 && score.asDouble() <= 10);
        }
        try { return mapper().convertValue(values, new TypeReference<List<Finding>>() {}); }
        catch (RuntimeException error) { throw new IOException("Invalid finding field types; contents are withheld"); }
    }
    @NonNull public static SeveritySummary parseSummary(@NonNull String json) throws IOException {
        JsonNode value = document(json);
        require(value.isObject());
        for (String key : List.of("critical", "high", "medium", "low", "info", "total")) require(value.path(key).isIntegralNumber() && value.path(key).canConvertToInt() && value.path(key).asInt() >= 0);
        return mapper().treeToValue(value, SeveritySummary.class);
    }
    @NonNull public static Campaign parseCampaign(@NonNull String json) throws IOException {
        JsonNode value = document(json);
        require(value.isObject() && text(value.get("id")) && text(value.get("status")));
        return mapper().treeToValue(value, Campaign.class);
    }
}
