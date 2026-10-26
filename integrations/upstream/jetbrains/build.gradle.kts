import org.jetbrains.intellij.platform.gradle.IntelliJPlatformType
import org.jetbrains.intellij.platform.gradle.TestFrameworkType

plugins {
    id("org.jetbrains.kotlin.jvm")
    id("org.jetbrains.intellij.platform")
}

group = providers.gradleProperty("group").get()
version = providers.gradleProperty("version").get()

kotlin {
    jvmToolchain(17)
}

repositories {
    mavenCentral()
    intellijPlatform {
        defaultRepositories()
    }
}

dependencies {
    // The Darkmoon Kotlin client (port of the frozen @darkmoon/client contract).
    implementation(project(":client"))

    testImplementation("junit:junit:4.13.2")

    intellijPlatform {
        // Target platform to compile against. IntelliJ IDEA Community 2025.2.x.
        intellijIdea("2025.2.6.2")
        testFramework(TestFrameworkType.Platform)
    }
}

intellijPlatform {
    pluginConfiguration {
        version = providers.gradleProperty("version")

        ideaVersion {
            // Compatibility floor. Compiled against 2025.2 but only uses long-stable
            // platform APIs (ToolWindowFactory, JBTable, PasswordSafe, DialogWrapper).
            sinceBuild = "243"
            // Open-ended upper bound for forward cross-version compatibility.
            untilBuild = provider { null }
        }
    }

    signing {
        certificateChain = providers.environmentVariable("CERTIFICATE_CHAIN")
        privateKey = providers.environmentVariable("PRIVATE_KEY")
        password = providers.environmentVariable("PRIVATE_KEY_PASSWORD")
    }

    publishing {
        token = providers.environmentVariable("PUBLISH_TOKEN")
        // Pre-release versions (e.g. 0.1.0-eap) go to a matching channel; otherwise default.
        channels = providers.gradleProperty("version").map {
            listOf(it.substringAfter('-', "").substringBefore('.').ifEmpty { "default" })
        }
    }

    pluginVerification {
        ides {
            // Verify against the compiled target (reuses the local cache). Widening
            // to the full recommended() matrix across the compatibility range is a
            // CI step; add `recommended()` there.
            create(IntelliJPlatformType.IntellijIdeaUltimate, "2025.2.6.2")
        }
    }
}

tasks {
    test {
        useJUnit()
        // Point the integration test at the darkmoon-ci test double + shared fixtures.
        // The child `node` process inherits DARKMOON_FIXTURES from this JVM's env.
        environment(
            "DARKMOON_FIXTURES",
            layout.projectDirectory.dir("src/test/resources/fixtures").asFile.absolutePath,
        )
        systemProperty(
            "darkmoon.stub",
            layout.projectDirectory.file("src/test/resources/stub/darkmoon-ci.mjs").asFile.absolutePath,
        )
        systemProperty(
            "darkmoon.bridge",
            layout.projectDirectory.file("src/main/resources/bridge/darkmoon-bridge.mjs").asFile.absolutePath,
        )
    }
}
