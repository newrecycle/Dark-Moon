package io.jenkins.plugins.darkmoon.contract;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import edu.umd.cs.findbugs.annotations.CheckForNull;
import edu.umd.cs.findbugs.annotations.NonNull;
import java.io.Serializable;

/** Aggregated, redaction-safe severity counts for a campaign (frozen contract §2.2). */
@JsonIgnoreProperties(ignoreUnknown = true)
public class SeveritySummary implements Serializable {

    private static final long serialVersionUID = 1L;

    private int critical;
    private int high;
    private int medium;
    private int low;
    private int info;
    private int total;

    public int getCritical() {
        return critical;
    }

    public void setCritical(int critical) {
        this.critical = critical;
    }

    public int getHigh() {
        return high;
    }

    public void setHigh(int high) {
        this.high = high;
    }

    public int getMedium() {
        return medium;
    }

    public void setMedium(int medium) {
        this.medium = medium;
    }

    public int getLow() {
        return low;
    }

    public void setLow(int low) {
        this.low = low;
    }

    public int getInfo() {
        return info;
    }

    public void setInfo(int info) {
        this.info = info;
    }

    public int getTotal() {
        return total;
    }

    public void setTotal(int total) {
        this.total = total;
    }

    /** Count for a given severity bucket. */
    public int countOf(@NonNull Severity severity) {
        switch (severity) {
            case CRITICAL:
                return critical;
            case HIGH:
                return high;
            case MEDIUM:
                return medium;
            case LOW:
                return low;
            case INFO:
            default:
                return info;
        }
    }

    /** Number of findings at or above {@code threshold}. */
    public int countAtLeast(@NonNull Severity threshold) {
        int sum = 0;
        for (Severity s : Severity.values()) {
            if (s.isAtLeast(threshold)) {
                sum += countOf(s);
            }
        }
        return sum;
    }

    /** The most severe bucket with a non-zero count, or {@code null} if empty. */
    @CheckForNull
    public Severity highestNonZero() {
        for (Severity s : Severity.values()) {
            if (countOf(s) > 0) {
                return s;
            }
        }
        return null;
    }
}
