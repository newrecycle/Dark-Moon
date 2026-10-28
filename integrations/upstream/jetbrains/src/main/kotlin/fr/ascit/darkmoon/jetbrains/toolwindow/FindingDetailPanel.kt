package fr.ascit.darkmoon.jetbrains.toolwindow

import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.ui.components.JBScrollPane
import fr.ascit.darkmoon.client.Finding
import fr.ascit.darkmoon.client.FindingEvidence
import fr.ascit.darkmoon.jetbrains.services.DarkmoonProjectService
import java.awt.BorderLayout
import javax.swing.JButton
import javax.swing.JEditorPane
import javax.swing.JPanel
import javax.swing.JToolBar

/**
 * Finding detail: description, evidence and remediation (§3.5). Evidence is
 * redaction-safe: nothing is fetched until the user asks, the redacted form is
 * the default, and the full (rehydrated) form requires an explicit local
 * confirmation — the two-key opt-in enforced again in the client (§4).
 */
class FindingDetailPanel(private val project: Project) : JPanel(BorderLayout()) {

    private val editor = JEditorPane("text/html", "").apply {
        isEditable = false
        putClientProperty(JEditorPane.HONOR_DISPLAY_PROPERTIES, true)
    }
    private val loadEvidenceButton = JButton("Load evidence (redacted)").apply { isEnabled = false }
    private val revealFullButton = JButton("Reveal full evidence…").apply { isEnabled = false }
    private var current: Finding? = null
    private var selection = 0L
    private val reveal = LocalReveal(project, this) { current?.let { render(it, null) } }

    init {
        val toolbar = JToolBar().apply {
            isFloatable = false
            add(loadEvidenceButton)
            add(revealFullButton)
        }
        add(toolbar, BorderLayout.NORTH)
        add(JBScrollPane(editor), BorderLayout.CENTER)

        loadEvidenceButton.addActionListener { reveal.revoke(); current?.let { render(it, null) } }
        revealFullButton.addActionListener { current?.let { confirmAndRevealFull(it.id) } }
        clear()
    }

    fun clear() {
        selection++
        reveal.revoke()
        current = null
        loadEvidenceButton.isEnabled = false
        revealFullButton.isEnabled = false
        editor.text = "<html><body style='font-family:sans-serif'><p>Select a finding.</p></body></html>"
        editor.caretPosition = 0
    }

    fun showFinding(finding: Finding) {
        selection++
        reveal.revoke()
        val metadata = finding.copy(description = null, remediation = null, endpoint = null, evidence = null)
        current = metadata
        loadEvidenceButton.isEnabled = true
        revealFullButton.isEnabled = true
        render(metadata, null)
    }

    private fun confirmAndRevealFull(id: String) {
        if (!reveal.eligible()) {
            Messages.showWarningDialog(project, "Full evidence requires a trusted, focused local IDE window.", "Evidence Hidden")
            return
        }
        val expected = reveal.origin()
        val version = selection
        val ok = Messages.showYesNoDialog(
            project,
            "The full evidence contains rehydrated real values (hosts, tokens, extracted data). " +
                "It will be shown locally in this panel only. Continue?",
            "Reveal Full Evidence",
            "Reveal Locally", "Cancel",
            Messages.getWarningIcon(),
        )
        if (ok == Messages.YES && selection == version && current?.id == id) reveal.issue(id, expected)?.let { loadEvidence(id, version, it) }
    }

    private fun loadEvidence(id: String, version: Long, grant: LocalReveal.Grant) {
        val service = DarkmoonProjectService.getInstance(project)
        val connection = service.connectionStamp()
        val campaignId = current?.campaignId
        object : Task.Backgroundable(project, "Loading Darkmoon evidence", true) {
            private var result: Finding? = null
            override fun run(indicator: ProgressIndicator) {
                try { result = service.findingWithEvidence(id, true, connection) } catch (_: Exception) { result = null }
            }
            override fun onSuccess() {
                val finding = result
                result = null
                if (project.isDisposed || selection != version || current?.id != id || !reveal.valid(grant)) return
                if (finding == null || finding.id != id || finding.campaignId != campaignId) { reveal.revoke(); return }
                // Keep only metadata in `current`; expiry cannot revive cached evidence.
                render(finding, finding.evidence)
            }
            override fun onCancel() { if (selection == version) reveal.revoke() }
        }.queue()
    }

    private fun render(f: Finding, evidence: FindingEvidence?) {
        val sb = StringBuilder("<html><body style='font-family:sans-serif;font-size:small'>")
        sb.append("<h2>").append(esc(f.title ?: "(untitled)")).append("</h2>")
        sb.append("<p><b>Severity:</b> ").append(f.severity.wire)
            .append(" &nbsp; <b>Status:</b> ").append(f.status.wire)
            .append(" &nbsp; <b>Edition:</b> ").append(f.edition.wire).append("</p>")
        val meta = buildList {
            f.category?.let { add("Category: ${esc(it)}") }
            f.cve?.let { add("CVE: ${esc(it)}") }
            f.cvssScore?.let { add("CVSS: $it") }
            f.cvssVector?.let { add(esc(it)) }
            f.mitreAttackId?.let { add("MITRE: ${esc(it)} ${esc(f.mitreAttackName ?: "")}") }
            f.endpoint?.let { add("Endpoint: ${esc(it)}") }
            f.discoveredByAgent?.let { add("Agent: ${esc(it)}") }
        }
        if (meta.isNotEmpty()) sb.append("<p>").append(meta.joinToString(" &nbsp;|&nbsp; ")).append("</p>")

        section(sb, "Description", f.description)
        section(sb, "Remediation", f.remediation)

        sb.append("<h3>Evidence</h3>")
        if (evidence == null) {
            sb.append("<p><i>Detailed evidence is hidden. Use the explicit trusted-local reveal action.</i></p>")
        } else {
            sb.append("<p><i>")
                .append(if (evidence.redacted) "Redacted (safe)." else "FULL — rehydrated real values, local only.")
                .append("</i></p>")
            list(sb, "Commands", evidence.commands)
            list(sb, "Payloads", evidence.payloads)
            pre(sb, "Request", evidence.rawRequest)
            pre(sb, "Response", evidence.rawResponse)
            pre(sb, "Extracted data", evidence.extractedData)
            list(sb, "Logs", evidence.logs)
            section(sb, "Explanation", evidence.explanation)
        }
        sb.append("</body></html>")
        editor.text = sb.toString()
        editor.caretPosition = 0
    }

    private fun section(sb: StringBuilder, title: String, body: String?) {
        if (body.isNullOrBlank()) return
        sb.append("<h3>").append(title).append("</h3><p>").append(esc(body).replace("\n", "<br>")).append("</p>")
    }

    private fun pre(sb: StringBuilder, title: String, body: String?) {
        if (body.isNullOrBlank()) return
        sb.append("<p><b>").append(title).append(":</b></p><pre style='white-space:pre-wrap'>")
            .append(esc(body)).append("</pre>")
    }

    private fun list(sb: StringBuilder, title: String, items: List<String>) {
        if (items.isEmpty()) return
        sb.append("<p><b>").append(title).append(":</b></p><ul>")
        items.forEach { sb.append("<li><code>").append(esc(it)).append("</code></li>") }
        sb.append("</ul>")
    }

    private fun esc(s: String): String = s
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
}
