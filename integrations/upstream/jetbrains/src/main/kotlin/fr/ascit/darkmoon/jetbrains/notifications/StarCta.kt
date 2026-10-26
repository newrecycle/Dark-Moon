package fr.ascit.darkmoon.jetbrains.notifications

import com.intellij.ide.BrowserUtil
import com.intellij.notification.Notification
import com.intellij.notification.NotificationAction
import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.project.Project
import fr.ascit.darkmoon.jetbrains.settings.DarkmoonSettings

/**
 * Non-intrusive, one-time GitHub star CTA (growth guardrails, §star).
 *
 * Shown as a calm INFORMATION balloon on the existing "Darkmoon" notification
 * group, and only after the very first real findings arrive. Never on plugin
 * load, never on an empty result, and never more than once (application-wide).
 * It carries only booleans in persistent state — no target or finding data ever
 * touches this path.
 */
object StarCta {

    private const val REPO_URL = "https://github.com/ASCIT31/Dark-Moon"
    private const val ENV_DISABLE = "DARKMOON_DISABLE_GROWTH_CTA"

    private const val TITLE = "Darkmoon"
    private const val CONTENT =
        "Darkmoon just delivered your first findings. " +
            "If it is useful, a star on GitHub helps the open source project."

    /**
     * Pure eligibility decision, factored out so it is fully unit-testable without
     * popping a balloon. Shows only when the growth CTA is enabled, the env opt-out
     * is not set, it has not been shown before, and there is at least one finding.
     */
    fun shouldShowStarCta(
        state: DarkmoonSettings.State,
        findingsCount: Int,
        envDisabled: Boolean,
    ): Boolean {
        if (envDisabled) return false
        if (!state.growthCtaEnabled) return false
        if (state.starCtaShown) return false
        return findingsCount > 0
    }

    /**
     * Whether DARKMOON_DISABLE_GROWTH_CTA is set to any truthy value. Absent, empty
     * or an explicit falsy token ("0"/"false"/"no"/"off") means "not disabled".
     */
    fun isDisabledByEnv(): Boolean {
        val raw = System.getenv(ENV_DISABLE) ?: return false
        return raw.trim().lowercase() !in FALSY
    }

    private val FALSY = setOf("", "0", "false", "no", "off")

    /**
     * Show the CTA once if eligible. Fail-safe: any failure here is swallowed so a
     * CTA problem can never break the findings view.
     */
    fun maybeShowStarCta(project: Project, findingsCount: Int) {
        try {
            val settings = DarkmoonSettings.getInstance()
            if (!shouldShowStarCta(settings.state, findingsCount, isDisabledByEnv())) return

            // Mark shown first so a repeat can never slip through, even on re-entry.
            settings.starCtaShown = true

            val notification = NotificationGroupManager.getInstance()
                .getNotificationGroup("Darkmoon")
                .createNotification(TITLE, CONTENT, NotificationType.INFORMATION)

            notification.addAction(object : NotificationAction("Star on GitHub") {
                override fun actionPerformed(e: AnActionEvent, n: Notification) {
                    BrowserUtil.browse(REPO_URL)
                    n.expire()
                }
            })
            notification.addAction(object : NotificationAction("Not now") {
                override fun actionPerformed(e: AnActionEvent, n: Notification) {
                    n.expire()
                }
            })
            notification.notify(project)
        } catch (t: Throwable) {
            // Never break the findings view because of a CTA failure.
        }
    }
}
