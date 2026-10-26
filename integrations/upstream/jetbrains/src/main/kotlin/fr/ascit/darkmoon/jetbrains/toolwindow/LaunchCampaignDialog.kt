package fr.ascit.darkmoon.jetbrains.toolwindow

import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.openapi.ui.ValidationInfo
import com.intellij.ui.components.JBCheckBox
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.FormBuilder
import fr.ascit.darkmoon.client.Capabilities
import fr.ascit.darkmoon.client.CapabilityGate
import fr.ascit.darkmoon.client.LaunchInput
import javax.swing.JComponent

/**
 * Launch-campaign form. Pro-only inputs (remediation → PR) are shown but
 * disabled unless the backend advertises the capability (§2.4). The plugin never
 * auto-runs remediation and never opens a PR itself: it only forwards the opt-in
 * plus an opaque credentialId to the backend.
 */
class LaunchCampaignDialog(
    project: Project,
    private val capabilities: Capabilities?,
) : DialogWrapper(project) {

    private val targetField = JBTextField()
    private val focusField = JBTextField()
    private val excludeField = JBTextField()
    private val severityField = JBTextField()
    private val formatField = JBTextField("markdown")

    private val remediateCheck = JBCheckBox("Run remediation → pull request (Pro)")
    private val gitRepoField = JBTextField()
    private val credentialIdField = JBTextField()

    init {
        title = "Launch Darkmoon Campaign"
        val canRemediate = CapabilityGate.canRemediate(capabilities)
        remediateCheck.isEnabled = canRemediate
        val updateRemediation = {
            val on = canRemediate && remediateCheck.isSelected
            gitRepoField.isEnabled = on
            credentialIdField.isEnabled = on
        }
        remediateCheck.addActionListener { updateRemediation() }
        gitRepoField.isEnabled = false
        credentialIdField.isEnabled = false
        init()
    }

    override fun createCenterPanel(): JComponent {
        targetField.columns = 36
        val builder = FormBuilder.createFormBuilder()
            .addLabeledComponent(JBLabel("Target (host/URL):"), targetField, 1, false)
            .addLabeledComponent(JBLabel("Focus (comma-sep):"), focusField, 1, false)
            .addLabeledComponent(JBLabel("Exclude (comma-sep):"), excludeField, 1, false)
            .addLabeledComponent(JBLabel("Min severity:"), severityField, 1, false)
            .addLabeledComponent(JBLabel("Report format:"), formatField, 1, false)
            .addSeparator()
            .addComponent(remediateCheck)

        if (!CapabilityGate.canRemediate(capabilities)) {
            builder.addComponentToRightColumn(
                JBLabel(CapabilityGate.proOnlyReason("Remediation"))
            )
        }
        builder
            .addLabeledComponent(JBLabel("Git repo (Pro):"), gitRepoField, 1, false)
            .addLabeledComponent(JBLabel("Credential ref (Pro):"), credentialIdField, 1, false)
        return builder.panel
    }

    override fun doValidate(): ValidationInfo? {
        if (targetField.text.isBlank()) return ValidationInfo("Target is required.", targetField)
        if (remediateCheck.isSelected && gitRepoField.text.isBlank()) {
            return ValidationInfo("A git repo is required for remediation.", gitRepoField)
        }
        return null
    }

    private fun csv(s: String): List<String>? =
        s.split(",").map { it.trim() }.filter { it.isNotEmpty() }.ifEmpty { null }

    fun getInput(): LaunchInput = LaunchInput(
        target = targetField.text.trim(),
        focus = csv(focusField.text),
        exclude = csv(excludeField.text),
        severity = severityField.text.trim().ifBlank { null },
        format = formatField.text.trim().ifBlank { null },
        remediate = if (remediateCheck.isSelected) true else null,
        gitRepo = gitRepoField.text.trim().ifBlank { null },
        credentialId = credentialIdField.text.trim().ifBlank { null },
    )
}
