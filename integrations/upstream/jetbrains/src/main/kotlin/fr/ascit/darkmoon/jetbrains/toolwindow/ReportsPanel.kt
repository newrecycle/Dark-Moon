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
        loadRedactedButton.addActionListener { campaignId?.let { load(it, full = false) } }
        openFullButton.addActionListener { campaignId?.let { confirmFull(it) } }
    }

    fun setCampaign(id: String?, target: String?) {
        campaignId = id
        loadRedactedButton.isEnabled = id != null
        openFullButton.isEnabled = id != null
        area.text = ""
        status.text = if (id == null) "Select a campaign in the Campaigns tab."
        else "Campaign $id${target?.let { " — $it" } ?: ""}"
    }

    private fun confirmFull(id: String) {
        val ok = Messages.showYesNoDialog(
            project,
            "The full report contains rehydrated real values (hosts, extracted data, evidence). " +
                "It will be displayed locally in this panel only. Continue?",
            "Open Full Report",
            "Open Locally", "Cancel",
            Messages.getWarningIcon(),
        )
        if (ok == Messages.YES) load(id, full = true)
    }

    private fun load(id: String, full: Boolean) {
        val service = DarkmoonProjectService.getInstance(project)
        object : Task.Backgroundable(project, "Loading Darkmoon report", true) {
            private var report: Report? = null
            private var error: String? = null
            override fun run(indicator: ProgressIndicator) {
                try { report = service.report(id, full) }
                catch (e: Exception) { error = e.message ?: e.javaClass.simpleName }
            }
            override fun onSuccess() {
                val r = report
                when {
                    r == null -> { area.text = "Failed to load report: ${error ?: "unknown error"}" }
                    !r.ready -> { area.text = "No report is available for this campaign yet."; status.text = "Report not ready" }
                    else -> {
                        area.text = r.content
                        area.caretPosition = 0
                        status.text = if (r.redacted) "Redaction-safe report" else "FULL report (local only)"
                    }
                }
            }
        }.queue()
    }
}
