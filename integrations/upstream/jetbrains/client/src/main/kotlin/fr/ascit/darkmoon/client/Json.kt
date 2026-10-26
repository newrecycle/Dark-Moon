package fr.ascit.darkmoon.client

import kotlinx.serialization.json.Json

/**
 * Shared JSON codec for the contract wire model. Lenient on unknown keys so the
 * plugin keeps working when the CLI/contract adds additive fields (§2.2 rule:
 * additive changes are non-breaking).
 */
internal val DarkmoonJson: Json = Json {
    ignoreUnknownKeys = true
    isLenient = true
    explicitNulls = false
    encodeDefaults = false
    coerceInputValues = true
}
