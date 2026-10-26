package fr.ascit.darkmoon.jetbrains.settings

import com.intellij.credentialStore.CredentialAttributes
import com.intellij.credentialStore.Credentials
import com.intellij.credentialStore.generateServiceName
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.diagnostic.thisLogger
import com.intellij.ide.passwordSafe.PasswordSafe

/**
 * Stores the Darkmoon Pro JWT in the IDE's PasswordSafe. The token never touches
 * DarkmoonSettings (which is serialized to disk), plugin logs, or process argv.
 *
 * PasswordSafe access is blocking and must not run on the EDT; every method here
 * asserts that and is only ever called from pooled/background threads.
 */
class DarkmoonSecretService {

    private val attributes: CredentialAttributes =
        CredentialAttributes(generateServiceName("Darkmoon", "pro-token"))

    private fun assertOffEdt() {
        check(!ApplicationManager.getApplication().isDispatchThread) {
            "DarkmoonSecretService must not be called on the EDT (PasswordSafe is blocking)."
        }
    }

    /** Returns the stored Pro token, or null. Off-EDT only. */
    fun getToken(): String? {
        assertOffEdt()
        return try {
            PasswordSafe.instance.getPassword(attributes)
        } catch (e: Exception) {
            thisLogger().warn("Failed to read Darkmoon token from PasswordSafe", e)
            null
        }
    }

    /** Stores (or clears, when null/blank) the Pro token. Off-EDT only. */
    fun setToken(token: String?) {
        assertOffEdt()
        try {
            if (token.isNullOrBlank()) {
                PasswordSafe.instance.set(attributes, null)
            } else {
                PasswordSafe.instance.set(attributes, Credentials(null, token))
            }
        } catch (e: Exception) {
            thisLogger().warn("Failed to persist Darkmoon token to PasswordSafe", e)
        }
    }

    companion object {
        fun getInstance(): DarkmoonSecretService =
            ApplicationManager.getApplication().getService(DarkmoonSecretService::class.java)
    }
}
