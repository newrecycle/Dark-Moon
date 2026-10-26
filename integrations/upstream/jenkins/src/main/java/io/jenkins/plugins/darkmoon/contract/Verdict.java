package io.jenkins.plugins.darkmoon.contract;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import edu.umd.cs.findbugs.annotations.CheckForNull;
import java.io.Serializable;
import java.util.List;

/**
 * The JSON payload printed by {@code darkmoon-ci run --json} (frozen contract):
 * {@code {campaignId, verdict, failOn, offending, total, reason}}.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public class Verdict implements Serializable {

    private static final long serialVersionUID = 1L;

    private String campaignId;
    private String verdict;
    private List<String> failOn;
    private int total;
    private String reason;

    @CheckForNull
    public String getCampaignId() {
        return campaignId;
    }

    public void setCampaignId(String campaignId) {
        this.campaignId = campaignId;
    }

    @CheckForNull
    public String getVerdict() {
        return verdict;
    }

    public void setVerdict(String verdict) {
        this.verdict = verdict;
    }

    @CheckForNull
    public List<String> getFailOn() {
        return failOn;
    }

    public void setFailOn(List<String> failOn) {
        this.failOn = failOn;
    }

    public int getTotal() {
        return total;
    }

    public void setTotal(int total) {
        this.total = total;
    }

    @CheckForNull
    public String getReason() {
        return reason;
    }

    public void setReason(String reason) {
        this.reason = reason;
    }

    public boolean failed() {
        return "fail".equalsIgnoreCase(verdict);
    }
}
