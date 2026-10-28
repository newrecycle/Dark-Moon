package fr.ascit.darkmoon.jetbrains.settings

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage
import fr.ascit.darkmoon.client.ClientMode

/** Non-secret settings only. Authentication stays in PasswordSafe. */
@State(name = "fr.ascit.darkmoon.DarkmoonSettings", storages = [Storage("darkmoon.xml")])
class DarkmoonSettings : PersistentStateComponent<DarkmoonSettings.State> {
    data class State(
        var mode: String = ClientMode.AUTO.wire,
        var baseUrl: String = "",
        var cliCommand: String = "bundled",
        var workingDir: String = "",
        var ossDataDir: String = "",
        var ossReportsDir: String = "",
        var growthCtaEnabled: Boolean = true,
        var starCtaShown: Boolean = false,
    )
    private var configuration = State()
    override fun getState(): State = configuration
    override fun loadState(value: State) { configuration = value }
    var mode: ClientMode
        get() = when (configuration.mode.lowercase()) { "oss" -> ClientMode.OSS; "pro" -> ClientMode.PRO; else -> ClientMode.AUTO }
        set(value) { configuration.mode = value.wire }
    var baseUrl: String
        get() = configuration.baseUrl
        set(value) { configuration.baseUrl = value.trim() }
    var cliCommand: String
        get() = configuration.cliCommand
        set(value) { configuration.cliCommand = value.trim() }
    var workingDir: String
        get() = configuration.workingDir
        set(value) { configuration.workingDir = value.trim() }
    var ossDataDir: String
        get() = configuration.ossDataDir
        set(value) { configuration.ossDataDir = value.trim() }
    var ossReportsDir: String
        get() = configuration.ossReportsDir
        set(value) { configuration.ossReportsDir = value.trim() }
    var growthCtaEnabled: Boolean
        get() = configuration.growthCtaEnabled
        set(value) { configuration.growthCtaEnabled = value }
    var starCtaShown: Boolean
        get() = configuration.starCtaShown
        set(value) { configuration.starCtaShown = value }
    fun commandTokens(): List<String> {
        val result = mutableListOf<String>()
        val token = StringBuilder()
        var quote: Char? = null
        var started = false
        var index = 0
        val command = cliCommand.trim()
        while (index < command.length) {
            val character = command[index]
            when {
                character == '\\' && index + 1 < command.length && (command[index + 1] == '"' || command[index + 1] == '\'') -> { token.append(command[++index]); started = true }
                quote != null && character == quote -> quote = null
                quote != null -> token.append(character)
                character == '"' || character == '\'' -> { quote = character; started = true }
                character.isWhitespace() -> { if (started) { result.add(token.toString()); token.clear(); started = false } }
                else -> { token.append(character); started = true }
            }
            index++
        }
        require(quote == null) { "Bridge command contains an unmatched quote" }
        if (started) result.add(token.toString())
        require(result.none { it.isEmpty() }) { "Bridge command contains an empty argument" }
        return result.ifEmpty { listOf("bundled") }
    }

    companion object {
        fun getInstance(): DarkmoonSettings = ApplicationManager.getApplication().getService(DarkmoonSettings::class.java)
    }
}
