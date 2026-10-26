package fr.ascit.darkmoon.jetbrains.settings

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.options.Configurable
import com.intellij.openapi.ui.ComboBox
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBPasswordField
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.FormBuilder
import java.awt.Dimension
import javax.swing.JCheckBox
import javax.swing.JComponent
import javax.swing.JPanel
import javax.swing.event.DocumentEvent
import javax.swing.event.DocumentListener

/**
 * Settings UI under Settings > Tools > Darkmoon. Non-secret fields persist in
 * DarkmoonSettings; the Pro token is read/written through PasswordSafe on a
 * pooled thread, never on the EDT.
 */
class DarkmoonSettingsConfigurable : Configurable {

    private val modeCombo = ComboBox(arrayOf("auto", "oss", "pro"))
    private val baseUrlField = JBTextField()
    private val cliCommandField = JBTextField()
    private val workingDirField = JBTextField()
    private val tokenField = JBPasswordField()
    private val growthCtaCheckbox = JCheckBox("Show the one-time GitHub star suggestion after the first findings")

    private var tokenTouched = false
    private var panel: JPanel? = null

    override fun getDisplayName(): String = "Darkmoon"

    override fun createComponent(): JComponent {
        tokenField.document.addDocumentListener(object : DocumentListener {
            override fun insertUpdate(e: DocumentEvent) { tokenTouched = true }
            override fun removeUpdate(e: DocumentEvent) { tokenTouched = true }
            override fun changedUpdate(e: DocumentEvent) { tokenTouched = true }
        })
        baseUrlField.columns = 32
        cliCommandField.columns = 32
        workingDirField.columns = 32

        val built = FormBuilder.createFormBuilder()
            .addLabeledComponent(JBLabel("Mode:"), modeCombo, 1, false)
            .addLabeledComponent(JBLabel("Pro base URL:"), baseUrlField, 1, false)
            .addComponentToRightColumn(JBLabel("Leave empty for OSS. Example: https://darkmoon.example.com"))
            .addLabeledComponent(JBLabel("darkmoon-ci command:"), cliCommandField, 1, false)
            .addComponentToRightColumn(JBLabel("On PATH, or e.g. \"node /opt/darkmoon/cli.cjs\""))
            .addLabeledComponent(JBLabel("Working directory:"), workingDirField, 1, false)
            .addLabeledComponent(JBLabel("Pro token (JWT):"), tokenField, 1, false)
            .addComponentToRightColumn(JBLabel("Stored in the IDE PasswordSafe, never in plugin settings."))
            .addComponent(growthCtaCheckbox)
            .addComponentToRightColumn(JBLabel("Can also be disabled with the DARKMOON_DISABLE_GROWTH_CTA environment variable."))
            .addComponentFillVertically(JPanel(), 0)
            .panel
        built.preferredSize = Dimension(560, 260)
        panel = built
        reset()
        return built
    }

    override fun isModified(): Boolean {
        val s = DarkmoonSettings.getInstance()
        return tokenTouched ||
            modeCombo.selectedItem != s.mode.wire ||
            baseUrlField.text != s.baseUrl ||
            cliCommandField.text != s.cliCommand ||
            workingDirField.text != s.workingDir ||
            growthCtaCheckbox.isSelected != s.growthCtaEnabled
    }

    override fun apply() {
        val s = DarkmoonSettings.getInstance()
        s.state.mode = (modeCombo.selectedItem as? String) ?: "auto"
        s.baseUrl = baseUrlField.text
        s.cliCommand = cliCommandField.text
        s.workingDir = workingDirField.text
        s.growthCtaEnabled = growthCtaCheckbox.isSelected
        if (tokenTouched) {
            val token = String(tokenField.password)
            // PasswordSafe is blocking → off the EDT.
            ApplicationManager.getApplication().executeOnPooledThread {
                DarkmoonSecretService.getInstance().setToken(token)
            }
            tokenTouched = false
        }
    }

    override fun reset() {
        val s = DarkmoonSettings.getInstance()
        modeCombo.selectedItem = s.mode.wire
        baseUrlField.text = s.baseUrl
        cliCommandField.text = s.cliCommand
        workingDirField.text = s.workingDir
        growthCtaCheckbox.isSelected = s.growthCtaEnabled
        tokenField.text = ""
        tokenTouched = false
        // Load the stored token off the EDT, then reflect it back on the EDT.
        ApplicationManager.getApplication().executeOnPooledThread {
            val token = DarkmoonSecretService.getInstance().getToken()
            if (token != null) {
                ApplicationManager.getApplication().invokeLater {
                    tokenField.text = token
                    tokenTouched = false
                }
            }
        }
    }
}
