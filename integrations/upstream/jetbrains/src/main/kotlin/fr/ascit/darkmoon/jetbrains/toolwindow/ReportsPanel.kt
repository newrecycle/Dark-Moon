package fr.ascit.darkmoon.jetbrains.toolwindow

import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.components.JBTextArea
import fr.ascit.darkmoon.client.Report
import fr.ascit.darkmoon.jetbrains.services.DarkmoonProjectService
import java.awt.BorderLayout
import javax.swing.JButton
import javax.swing.JPanel
import javax.swing.JToolBar

/**
 * Reports tab (§3.5 / §4). The report is redaction-safe by default; the full,
 * rehydrated report is fetched only on an explicit, confirmed, local action and
 * is shown in-panel only — never written to disk or logs by the plugin.
 */
class ReportsPanel(private val project: Project) : JPanel(BorderLayout()) {

    private val status = JBLabel("Select a campaign in the Campaigns tab.")
    private val loadRedactedButton = JButton("Load report (redacted)").apply { isEnabled = false }
    private val openFullButton = JButton("Open full report locally…").apply { isEnabled = false }
    private val area = JBTextArea().apply {
        isEditable = false
        lineWrap = true
        wrapStyleWord = true
    }
    private var campaignId: String? = null
    private var selection = 0L
    private val reveal = LocalReveal(project, this) { preview() }

    init {
        val toolbar = JToolBar().apply {
            isFloatable = false
            add(loadRedactedButton)
            add(openFullButton)
            addSeparator()
            add(status)
        }
        add(toolbar, BorderLayout.NORTH)
        add(JBScrollPane(area), BorderLayout.CENTER)
        loadRedactedButton.addActionListener { reveal.revoke(); preview() }
        openFullButton.addActionListener { campaignId?.let { confirmFull(it) } }
    }

    fun setCampaign(id: String?, @Suppress("UNUSED_PARAMETER") target: String?) {
        selection++
        reveal.revoke()
        campaignId = id
        loadRedactedButton.isEnabled = id != null
        openFullButton.isEnabled = id != null
        area.text = ""
        status.text = if (id == null) "Select a campaign in the Campaigns tab."
        else "Campaign $id"
        preview()
    }

    private fun confirmFull(id: String) {
        if (!reveal.eligible()) {
            Messages.showWarningDialog(project, "Full reports require a trusted, focused local IDE window.", "Report Hidden")
            return
        }
        val expected = reveal.origin()
        val version = selection
        val ok = Messages.showYesNoDialog(
            project,
            "The full report contains rehydrated real values (hosts, extracted data, evidence). " +
                "It will be displayed locally in this panel only. Continue?",
            "Open Full Report",
            "Open Locally", "Cancel",
            Messages.getWarningIcon(),
        )
        if (ok == Messages.YES && version == selection && campaignId == id) reveal.issue(id, expected)?.let { load(id, version, it) }
    }

    private fun preview() {
        val id = campaignId
        val campaign = DarkmoonProjectService.getInstance(project).campaigns.firstOrNull { it.id == id }
        area.text = if (campaign == null) "Refresh and select a campaign to view current summary metadata." else buildString {
            append("Campaign ").append(campaign.id).append("\nStatus: ").append(campaign.status.wire)
            val counts = campaign.severity
            append("\nRetained summary counts: critical=").append(counts.critical).append(", high=").append(counts.high)
            append(", medium=").append(counts.medium).append(", low=").append(counts.low).append(", info=").append(counts.info)
            append("\n\nDetailed report text and evidence are hidden. Explicit local reveal expires after at most 60 seconds.")
        }
        area.caretPosition = 0
        status.text = "Report summary — detailed text hidden"
    }

    private fun load(id: String, version: Long, grant: LocalReveal.Grant) {
        val service = DarkmoonProjectService.getInstance(project)
        val connection = service.connectionStamp()
        object : Task.Backgroundable(project, "Loading Darkmoon report", true) {
            private var report: Report? = null
            override fun run(indicator: ProgressIndicator) {
                try { report = service.report(id, true, connection) } catch (_: Exception) { report = null }
            }
            override fun onSuccess() {
                val result = report
                report = null
                if (project.isDisposed || selection != version || campaignId != id || !reveal.valid(grant)) return
                if (result == null || !result.ready || result.campaignId != id) {
                    reveal.revoke()
                    status.text = "Report unavailable for this selection and connection"
                    return
                }
                area.text = result.content
                area.caretPosition = 0
                status.text = if (result.redacted) "Backend returned a redacted report" else "Full report — expires within 60 seconds"
            }
            override fun onCancel() { if (selection == version) reveal.revoke() }
        }.queue()
    }
}
