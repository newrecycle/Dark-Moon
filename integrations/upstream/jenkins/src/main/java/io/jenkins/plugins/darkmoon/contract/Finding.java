package io.jenkins.plugins.darkmoon.contract;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import edu.umd.cs.findbugs.annotations.CheckForNull;
import java.io.Serializable;

/**
 * A normalized, redaction-safe finding from the frozen {@code @darkmoon/client}
 * contract (§2.2). Evidence (raw request/response, extracted data, payloads) is
 * intentionally NOT modelled here: the CLI emits it as {@code null} unless the
 * operator explicitly opts in, so this object is always safe to render in the
 * Jenkins UI and SARIF. See §4 (threat model).
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public class Finding implements Serializable {

    private static final long serialVersionUID = 1L;

    private String id;
    private String title;
    private Severity severity = Severity.INFO;
    private String status;
    private String category;
    private String cve;

    @JsonProperty("cvssScore")
    private Double cvssScore;

    @JsonProperty("cvssVector")
    private String cvssVector;

    @JsonProperty("mitreAttackId")
    private String mitreAttackId;

    @JsonProperty("mitreAttackName")
    private String mitreAttackName;

    private String endpoint;
    private String description;
    private String remediation;

    @JsonProperty("discoveredByAgent")
    private String discoveredByAgent;

    @JsonProperty("discoveredAt")
    private String discoveredAt;

    @CheckForNull
    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    @CheckForNull
    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public Severity getSeverity() {
        return severity == null ? Severity.INFO : severity;
    }

    public void setSeverity(Severity severity) {
        this.severity = severity;
    }

    @CheckForNull
    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    @CheckForNull
    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }

    @CheckForNull
    public String getCve() {
        return cve;
    }

    public void setCve(String cve) {
        this.cve = cve;
    }

    @CheckForNull
    public Double getCvssScore() {
        return cvssScore;
    }

    public void setCvssScore(Double cvssScore) {
        this.cvssScore = cvssScore;
    }

    @CheckForNull
    public String getCvssVector() {
        return cvssVector;
    }

    public void setCvssVector(String cvssVector) {
        this.cvssVector = cvssVector;
    }

    @CheckForNull
    public String getMitreAttackId() {
        return mitreAttackId;
    }

    public void setMitreAttackId(String mitreAttackId) {
        this.mitreAttackId = mitreAttackId;
    }

    @CheckForNull
    public String getMitreAttackName() {
        return mitreAttackName;
    }

    public void setMitreAttackName(String mitreAttackName) {
        this.mitreAttackName = mitreAttackName;
    }

    @CheckForNull
    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    @CheckForNull
    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    @CheckForNull
    public String getRemediation() {
        return remediation;
    }

    public void setRemediation(String remediation) {
        this.remediation = remediation;
    }

    @CheckForNull
    public String getDiscoveredByAgent() {
        return discoveredByAgent;
    }

    public void setDiscoveredByAgent(String discoveredByAgent) {
        this.discoveredByAgent = discoveredByAgent;
    }

    @CheckForNull
    public String getDiscoveredAt() {
        return discoveredAt;
    }

    public void setDiscoveredAt(String discoveredAt) {
        this.discoveredAt = discoveredAt;
    }

    /** Stable SARIF ruleId: prefer category, else id, else a constant. */
    public String ruleId() {
        if (category != null && !category.isBlank()) {
            return "darkmoon/" + category.trim();
        }
        if (id != null && !id.isBlank()) {
            return "darkmoon/" + id.trim();
        }
        return "darkmoon/finding";
    }
}
