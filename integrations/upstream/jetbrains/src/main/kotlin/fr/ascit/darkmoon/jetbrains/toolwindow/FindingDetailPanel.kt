package fr.ascit.darkmoon.jetbrains.toolwindow

import com.intellij.openapi.application.ApplicationManager
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

    init {
        val toolbar = JToolBar().apply {
            isFloatable = false
            add(loadEvidenceButton)
            add(revealFullButton)
        }
        add(toolbar, BorderLayout.NORTH)
        add(JBScrollPane(editor), BorderLayout.CENTER)

        loadEvidenceButton.addActionListener { current?.let { loadEvidence(it.id, full = false) } }
        revealFullButton.addActionListener { current?.let { confirmAndRevealFull(it.id) } }
        clear()
    }

    fun clear() {
        current = null
        loadEvidenceButton.isEnabled = false
        revealFullButton.isEnabled = false
        editor.text = "<html><body style='font-family:sans-serif'><p>Select a finding.</p></body></html>"
        editor.caretPosition = 0
    }

    fun showFinding(finding: Finding) {
        current = finding
        loadEvidenceButton.isEnabled = true
        revealFullButton.isEnabled = true
        render(finding, finding.evidence)
    }

    private fun confirmAndRevealFull(id: String) {
        val ok = Messages.showYesNoDialog(
            project,
            "The full evidence contains rehydrated real values (hosts, tokens, extracted data). " +
                "It will be shown locally in this panel only. Continue?",
            "Reveal Full Evidence",
            "Reveal Locally", "Cancel",
            Messages.getWarningIcon(),
        )
        if (ok == Messages.YES) loadEvidence(id, full = true)
    }

    private fun loadEvidence(id: String, full: Boolean) {
        val service = DarkmoonProjectService.getInstance(project)
        object : Task.Backgroundable(project, "Loading Darkmoon evidence", true) {
            private var result: Finding? = null
            private var error: String? = null
            override fun run(indicator: ProgressIndicator) {
                try {
                    result = service.findingWithEvidence(id, full)
                } catch (e: Exception) {
                    error = e.message ?: e.javaClass.simpleName
                }
            }
            override fun onSuccess() {
                val f = result
                if (f != null) { current = f; render(f, f.evidence) }
                else editorAppendError(error)
            }
        }.queue()
    }

    private fun editorAppendError(msg: String?) {
        ApplicationManager.getApplication().assertIsDispatchThread()
        editor.text = "<html><body style='font-family:sans-serif'><p style='color:#c0392b'>" +
            "Failed to load evidence: ${esc(msg ?: "unknown error")}</p></body></html>"
        editor.caretPosition = 0
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
            sb.append("<p><i>Not loaded. Use “Load evidence (redacted)”.</i></p>")
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
