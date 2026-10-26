package fr.ascit.darkmoon.jetbrains

import com.intellij.DynamicBundle
import org.jetbrains.annotations.NonNls
import org.jetbrains.annotations.PropertyKey

@NonNls
private const val BUNDLE = "messages.DarkmoonBundle"

object DarkmoonBundle : DynamicBundle(BUNDLE) {
    @JvmStatic
    operator fun get(@PropertyKey(resourceBundle = BUNDLE) key: String, vararg params: Any): String =
        getMessage(key, *params)
}
