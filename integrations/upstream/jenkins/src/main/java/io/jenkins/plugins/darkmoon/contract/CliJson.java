package io.jenkins.plugins.darkmoon.contract;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import edu.umd.cs.findbugs.annotations.NonNull;
import java.io.IOException;
import java.util.List;

/** Parses the JSON documents printed by {@code darkmoon-ci} into the contract POJOs. */
public final class CliJson {

    private CliJson() {}

    private static ObjectMapper mapper() {
        return new ObjectMapper()
                .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false)
                .configure(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY, true);
    }

    @NonNull
    public static Verdict parseVerdict(@NonNull String json) throws IOException {
        Verdict v = mapper().readValue(trim(json), Verdict.class);
        return v == null ? new Verdict() : v;
    }

    @NonNull
    public static List<Finding> parseFindings(@NonNull String json) throws IOException {
        return mapper().readValue(trim(json), new TypeReference<List<Finding>>() {});
    }

    @NonNull
    public static SeveritySummary parseSummary(@NonNull String json) throws IOException {
        SeveritySummary s = mapper().readValue(trim(json), SeveritySummary.class);
        return s == null ? new SeveritySummary() : s;
    }

    @NonNull
    public static Campaign parseCampaign(@NonNull String json) throws IOException {
        Campaign c = mapper().readValue(trim(json), Campaign.class);
        return c == null ? new Campaign() : c;
    }

    /**
     * Tolerate leading non-JSON noise (a stray banner line) by trimming to the
     * first {@code {} or {@code [}. Keeps parsing robust without masking real errors.
     */
    private static String trim(String json) {
        if (json == null) {
            return "";
        }
        int brace = json.indexOf('{');
        int bracket = json.indexOf('[');
        int start;
        if (brace < 0) {
            start = bracket;
        } else if (bracket < 0) {
            start = brace;
        } else {
            start = Math.min(brace, bracket);
        }
        return start > 0 ? json.substring(start) : json;
    }
}
