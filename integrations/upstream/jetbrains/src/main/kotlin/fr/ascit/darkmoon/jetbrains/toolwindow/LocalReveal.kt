package fr.ascit.darkmoon.jetbrains.toolwindow

import com.intellij.ide.trustedProjects.TrustedProjects
import com.intellij.idea.AppMode
import com.intellij.openapi.Disposable
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.Disposer
import com.intellij.util.PlatformUtils
import fr.ascit.darkmoon.jetbrains.services.DarkmoonProjectService
import fr.ascit.darkmoon.jetbrains.settings.DarkmoonSecretService
import fr.ascit.darkmoon.jetbrains.settings.DarkmoonSettings
import java.awt.KeyboardFocusManager
import java.awt.event.HierarchyEvent
import java.beans.PropertyChangeListener
import javax.swing.JComponent
import javax.swing.SwingUtilities
import javax.swing.Timer

/** A UI grant holds identity and timing only, never report/evidence content. */
internal class LocalReveal(private val project: Project, private val component: JComponent, private val onRevoke: () -> Unit) : Disposable {
    data class Origin(val connection: Long, val secret: Long, val mode: String, val url: String, val command: String, val directory: String, val data: String, val reports: String)
    class Grant(val id: String, val origin: Origin, val expires: Long)
    private var grant: Grant? = null
    private val timer = Timer(200) { grant?.let { if (!valid(it)) revoke() } }
    private val focus = PropertyChangeListener { SwingUtilities.invokeLater { if (!eligible()) revoke() } }

    init {
        Disposer.register(project, this)
        KeyboardFocusManager.getCurrentKeyboardFocusManager().addPropertyChangeListener("activeWindow", focus)
        component.addHierarchyListener { if (it.changeFlags and HierarchyEvent.SHOWING_CHANGED.toLong() != 0L && !component.isShowing) revoke() }
    }

    fun origin(): Origin {
        val settings = DarkmoonSettings.getInstance()
        return Origin(DarkmoonProjectService.getInstance(project).revision, DarkmoonSecretService.getInstance().revision,
            settings.mode.wire, settings.baseUrl, settings.cliCommand, settings.workingDir, settings.ossDataDir, settings.ossReportsDir)
    }

    fun eligible(): Boolean = runCatching {
        !project.isDisposed && !AppMode.isRemoteDevHost() && !PlatformUtils.isJetBrainsClient() &&
            TrustedProjects.isProjectTrusted(project) && component.isShowing &&
            SwingUtilities.getWindowAncestor(component)?.isActive == true
    }.getOrDefault(false)

    fun issue(id: String, expected: Origin): Grant? {
        revoke()
        if (!eligible() || origin() != expected) return null
        return Grant(id, expected, System.nanoTime() + 60_000_000_000L).also { grant = it; timer.start() }
    }

    fun valid(value: Grant): Boolean = grant === value && System.nanoTime() < value.expires && eligible() && origin() == value.origin

    fun revoke() {
        val previous = grant
        grant = null
        timer.stop()
        if (previous != null) onRevoke()
    }

    override fun dispose() {
        revoke()
        KeyboardFocusManager.getCurrentKeyboardFocusManager().removePropertyChangeListener("activeWindow", focus)
    }
}
