package fr.ascit.darkmoon.jetbrains.services

import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption

/** Extract the shipped bridge and SDK together; no runtime install or download. */
internal object BundledBridge {
    private val directory: Path by lazy {
        val root = Files.createTempDirectory("darkmoon-bridge-")
        root.toFile().deleteOnExit()
        val client = Files.createDirectories(root.resolve("client"))
        client.toFile().deleteOnExit()
        for (name in listOf("darkmoon-bridge.mjs", "client/index.mjs", "client/LICENSE", "client/ZOD-LICENSE", "client/snapshot.json")) {
            val destination = root.resolve(name)
            val resource = BundledBridge::class.java.classLoader.getResourceAsStream("bridge/$name")
                ?: error("The packaged Darkmoon bridge is incomplete")
            resource.use { Files.copy(it, destination, StandardCopyOption.REPLACE_EXISTING) }
            destination.toFile().deleteOnExit()
        }
        root
    }
    fun command(): List<String> = listOf("node", directory.resolve("darkmoon-bridge.mjs").toString())
    fun module(): String = directory.resolve("client/index.mjs").toUri().toString()
}
