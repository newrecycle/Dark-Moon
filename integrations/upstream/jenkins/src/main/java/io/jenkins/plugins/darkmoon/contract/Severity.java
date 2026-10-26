package io.jenkins.plugins.darkmoon.contract;

import com.fasterxml.jackson.annotation.JsonCreator;
import edu.umd.cs.findbugs.annotations.CheckForNull;
import edu.umd.cs.findbugs.annotations.NonNull;
import java.util.Locale;

/**
 * Canonical, lowercase severity set from the frozen {@code @darkmoon/client}
 * contract (§2.2): {@code critical, high, medium, low, info}. Ordinal order is
 * most-severe first so {@link #isAtLeast(Severity)} is a simple comparison.
 */
public enum Severity {
    CRITICAL("critical", "error"),
    HIGH("high", "error"),
    MEDIUM("medium", "warning"),
    LOW("low", "note"),
    INFO("info", "note");

    private final String id;
    private final String sarifLevel;

    Severity(String id, String sarifLevel) {
        this.id = id;
        this.sarifLevel = sarifLevel;
    }

    @NonNull
    public String id() {
        return id;
    }

    /** SARIF 2.1.0 result level mapping (error/warning/note). */
    @NonNull
    public String sarifLevel() {
        return sarifLevel;
    }

    /** True when {@code this} is at least as severe as {@code threshold}. */
    public boolean isAtLeast(@NonNull Severity threshold) {
        // Lower ordinal == more severe.
        return this.ordinal() <= threshold.ordinal();
    }

    /**
     * Parse a backend severity string. Unknown / null values normalize to
     * {@link #INFO} so an unexpected label can never silently suppress a gate.
     */
    @JsonCreator
    @NonNull
    public static Severity fromString(@CheckForNull String value) {
        if (value == null) {
            return INFO;
        }
        String v = value.trim().toLowerCase(Locale.ROOT);
        switch (v) {
            case "critical":
                return CRITICAL;
            case "high":
                return HIGH;
            case "medium":
            case "moderate":
                return MEDIUM;
            case "low":
                return LOW;
            case "info":
            case "informational":
            case "none":
            default:
                return INFO;
        }
    }
}
