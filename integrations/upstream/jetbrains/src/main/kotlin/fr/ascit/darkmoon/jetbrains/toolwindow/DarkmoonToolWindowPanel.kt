package fr.ascit.darkmoon.jetbrains.toolwindow

import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.ui.JBSplitter
import com.intellij.ui.SearchTextField
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.components.JBTabbedPane
import com.intellij.ui.table.JBTable
import fr.ascit.darkmoon.client.Campaign
import fr.ascit.darkmoon.client.Capabilities
import fr.ascit.darkmoon.client.CapabilityGate
import fr.ascit.darkmoon.client.Edition
import fr.ascit.darkmoon.client.Finding
import fr.ascit.darkmoon.client.Severity
import fr.ascit.darkmoon.jetbrains.DarkmoonBundle
import fr.ascit.darkmoon.jetbrains.notifications.StarCta
import fr.ascit.darkmoon.jetbrains.services.DarkmoonProjectService
import fr.ascit.darkmoon.jetbrains.settings.DarkmoonSettings
import java.awt.BorderLayout
import javax.swing.JButton
import javax.swing.JComboBox
import javax.swing.JPanel
import javax.swing.JToolBar
import javax.swing.ListSelectionModel
import javax.swing.RowFilter
import javax.swing.table.TableRowSorter

/**
 * Root Darkmoon tool window panel: Campaigns, Vulnerabilities (with a sortable /
 * filterable / searchable table and a finding-detail pane), and Reports. All
 * backend calls run on background threads; Pro-only actions degrade cleanly on
 * OSS (§2.4). No infrastructure graph and no auto-PR are exposed (§4).
 */
class DarkmoonToolWindowPanel(private val project: Project) : JPanel(BorderLayout()) {

    private val service = DarkmoonProjectService.getInstance(project)

    private val statusLabel = JBLabel(DarkmoonBundle["status.notConfigured"])
    private val refreshButton = JButton(DarkmoonBundle["action.refresh.text"])
    private val launchButton = JButton(DarkmoonBundle["action.launch.text"]).apply { isEnabled = false }

    private val campaignsModel = CampaignsTableModel()
    private val campaignsTable = JBTable(campaignsModel).apply {
        setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        autoCreateRowSorter = true
    }

    private val vulnModel = VulnerabilitiesTableModel()
    private val vulnTable = JBTable(vulnModel).apply {
        setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
    }
    private val vulnSorter = TableRowSorter(vulnModel).apply {
        setComparator(0, VulnerabilitiesTableModel.SEVERITY_COMPARATOR)
    }
    private val searchField = SearchTextField()
    private val severityFilter = JComboBox(
        arrayOf("All severities", "critical", "high", "medium", "low", "info")
    )

    private val findingDetail = FindingDetailPanel(project)
    private val reportsPanel = ReportsPanel(project)

    private var capabilities: Capabilities? = null

    init {
        vulnTable.rowSorter = vulnSorter

        add(buildToolbar(), BorderLayout.NORTH)

        val tabs = JBTabbedPane()
        tabs.addTab(DarkmoonBundle["tab.campaigns"], buildCampaignsTab())
        tabs.addTab(DarkmoonBundle["tab.vulnerabilities"], buildVulnerabilitiesTab())
        tabs.addTab(DarkmoonBundle["tab.reports"], reportsPanel)
        add(tabs, BorderLayout.CENTER)

        wireSelections()
        refreshButton.addActionListener { refresh() }
        launchButton.addActionListener { launch() }

        // Initial load.
        refresh()
    }

    private fun buildToolbar(): JComponent2 {
        val bar = JToolBar()
        bar.isFloatable = false
        bar.add(refreshButton)
        bar.add(launchButton)
        bar.addSeparator()
        bar.add(statusLabel)
        return bar
    }

    private fun buildCampaignsTab(): JPanel =
        JPanel(BorderLayout()).apply { add(JBScrollPane(campaignsTable), BorderLayout.CENTER) }

    private fun buildVulnerabilitiesTab(): JPanel {
        val filters = JPanel(BorderLayout())
        val left = JPanel()
        left.add(JBLabel(DarkmoonBundle["search.placeholder"] + ":"))
        left.add(searchField)
        filters.add(left, BorderLayout.WEST)
        filters.add(severityFilter, BorderLayout.EAST)

        val tableWithFilters = JPanel(BorderLayout()).apply {
            add(filters, BorderLayout.NORTH)
            add(JBScrollPane(vulnTable), BorderLayout.CENTER)
        }

        val splitter = JBSplitter(true, 0.5f).apply {
            firstComponent = tableWithFilters
            secondComponent = findingDetail
        }
        val installFilter = { applyVulnFilter() }
        searchField.addDocumentListener(object : javax.swing.event.DocumentListener {
            override fun insertUpdate(e: javax.swing.event.DocumentEvent) = installFilter()
            override fun removeUpdate(e: javax.swing.event.DocumentEvent) = installFilter()
            override fun changedUpdate(e: javax.swing.event.DocumentEvent) = installFilter()
        })
        severityFilter.addActionListener { applyVulnFilter() }

        return JPanel(BorderLayout()).apply { add(splitter, BorderLayout.CENTER) }
    }

    private fun applyVulnFilter() {
        val query = searchField.text.trim()
        val sevSel = severityFilter.selectedItem as? String
        val filters = mutableListOf<RowFilter<VulnerabilitiesTableModel, Int>>()
        if (query.isNotEmpty()) {
            filters += RowFilter.regexFilter("(?i)" + RegexEscape.quote(query))
        }
        if (sevSel != null && sevSel != "All severities") {
            filters += object : RowFilter<VulnerabilitiesTableModel, Int>() {
                override fun include(entry: Entry<out VulnerabilitiesTableModel, out Int>): Boolean {
                    val sev = entry.getValue(0) as? Severity ?: return false
                    return sev.wire == sevSel
                }
            }
        }
        vulnSorter.rowFilter = if (filters.isEmpty()) null else RowFilter.andFilter(filters)
    }

    private fun wireSelections() {
        campaignsTable.selectionModel.addListSelectionListener { e ->
            if (e.valueIsAdjusting) return@addListSelectionListener
            val viewRow = campaignsTable.selectedRow
            if (viewRow < 0) return@addListSelectionListener
            val campaign = campaignsModel.campaignAt(campaignsTable.convertRowIndexToModel(viewRow))
                ?: return@addListSelectionListener
            reportsPanel.setCampaign(campaign.id, campaign.target)
            findingDetail.clear()
            loadFindings(campaign)
        }
        vulnTable.selectionModel.addListSelectionListener { e ->
            if (e.valueIsAdjusting) return@addListSelectionListener
            val viewRow = vulnTable.selectedRow
            if (viewRow < 0) return@addListSelectionListener
            val finding = vulnModel.findingAt(vulnTable.convertRowIndexToModel(viewRow))
                ?: return@addListSelectionListener
            findingDetail.showFinding(finding)
        }
    }

    private fun refresh() {
        refreshButton.isEnabled = false
        object : Task.Backgroundable(project, "Refreshing Darkmoon", true) {
            private var caps: Capabilities? = null
            private var camps: List<Campaign> = emptyList()
            private var error: String? = null
            override fun run(indicator: ProgressIndicator) {
                try {
                    caps = service.refresh()
                    camps = service.campaigns
                } catch (e: Exception) {
                    error = e.message ?: e.javaClass.simpleName
                }
            }
            override fun onSuccess() {
                refreshButton.isEnabled = true
                val c = caps
                capabilities = c
                if (c == null) {
                    statusLabel.text = (DarkmoonBundle["status.unavailable"]) + (error?.let { " ($it)" } ?: "")
                    launchButton.isEnabled = false
                    return
                }
                campaignsModel.setCampaigns(camps)
                launchButton.isEnabled = CapabilityGate.canLaunchCampaign(c)
                statusLabel.text = buildString {
                    append(if (c.edition == Edition.PRO) DarkmoonBundle["status.pro"] else DarkmoonBundle["status.oss"])
                    append(" (v").append(c.version).append(")")
                    append(" — ").append(camps.size).append(" campaigns")
                }
                notifyWarnings(c)
            }
        }.queue()
    }

    private fun notifyWarnings(caps: Capabilities) {
        if (caps.warnings.isEmpty()) return
        val group = NotificationGroupManager.getInstance().getNotificationGroup("Darkmoon")
        caps.warnings.forEach {
            group.createNotification("Darkmoon", it, NotificationType.WARNING).notify(project)
        }
    }

    private fun loadFindings(campaign: Campaign) {
        object : Task.Backgroundable(project, "Loading findings for ${campaign.id}", true) {
            private var findings: List<Finding> = emptyList()
            private var error: String? = null
            override fun run(indicator: ProgressIndicator) {
                try { findings = service.findings(campaign.id) }
                catch (e: Exception) { error = e.message ?: e.javaClass.simpleName }
            }
            override fun onSuccess() {
                vulnModel.setFindings(findings)
                if (error != null) statusLabel.text = "Findings error: $error"
                // First real result: offer a one-time, non-intrusive GitHub star CTA.
                // Guarded (non-empty + once-only + opt-out) inside; fail-safe there.
                if (error == null && findings.isNotEmpty()) {
                    StarCta.maybeShowStarCta(project, findings.size)
                }
            }
        }.queue()
    }

    private fun launch() {
        val dialog = LaunchCampaignDialog(project, capabilities)
        if (!dialog.showAndGet()) return
        val input = dialog.getInput()
        object : Task.Backgroundable(project, "Launching Darkmoon campaign", true) {
            private var ok = false
            private var error: String? = null
            override fun run(indicator: ProgressIndicator) {
                try { service.launch(input); ok = true }
                catch (e: Exception) { error = e.message ?: e.javaClass.simpleName }
            }
            override fun onSuccess() {
                if (ok) {
                    Messages.showInfoMessage(project, "Campaign launched against ${input.target}.", "Darkmoon")
                    refresh()
                } else {
                    Messages.showErrorDialog(project, error ?: "Launch failed.", "Darkmoon")
                }
            }
        }.queue()
    }
}

/** Local alias so buildToolbar can return a Swing component without importing JComponent twice. */
private typealias JComponent2 = javax.swing.JComponent

/** Small regex-quote helper (avoids importing java.util.regex.Pattern at call site). */
private object RegexEscape {
    fun quote(s: String): String = java.util.regex.Pattern.quote(s)
}
