package io.jenkins.plugins.darkmoon.contract;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import edu.umd.cs.findbugs.annotations.CheckForNull;
import java.io.Serializable;

/** A normalized campaign header from the frozen contract (§2.2). */
@JsonIgnoreProperties(ignoreUnknown = true)
public class Campaign implements Serializable {

    private static final long serialVersionUID = 1L;

    private String id;
    private String target;
    private String status;

    @JsonProperty("overallRisk")
    private String overallRisk;

    @JsonProperty("reportPath")
    private String reportPath;

    @JsonProperty("executiveSummary")
    private String executiveSummary;

    @JsonProperty("durationSeconds")
    private Long durationSeconds;

    private String edition;

    private SeveritySummary severity = new SeveritySummary();

    @CheckForNull
    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    @CheckForNull
    public String getTarget() {
        return target;
    }

    public void setTarget(String target) {
        this.target = target;
    }

    @CheckForNull
    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    @CheckForNull
    public String getOverallRisk() {
        return overallRisk;
    }

    public void setOverallRisk(String overallRisk) {
        this.overallRisk = overallRisk;
    }

    @CheckForNull
    public String getReportPath() {
        return reportPath;
    }

    public void setReportPath(String reportPath) {
        this.reportPath = reportPath;
    }

    @CheckForNull
    public String getExecutiveSummary() {
        return executiveSummary;
    }

    public void setExecutiveSummary(String executiveSummary) {
        this.executiveSummary = executiveSummary;
    }

    @CheckForNull
    public Long getDurationSeconds() {
        return durationSeconds;
    }

    public void setDurationSeconds(Long durationSeconds) {
        this.durationSeconds = durationSeconds;
    }

    @CheckForNull
    public String getEdition() {
        return edition;
    }

    public void setEdition(String edition) {
        this.edition = edition;
    }

    public SeveritySummary getSeverity() {
        return severity == null ? new SeveritySummary() : severity;
    }

    public void setSeverity(SeveritySummary severity) {
        this.severity = severity;
    }
}
