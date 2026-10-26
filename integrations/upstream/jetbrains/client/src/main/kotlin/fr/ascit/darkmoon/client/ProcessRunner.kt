package fr.ascit.darkmoon.client

import java.io.BufferedReader
import java.io.File
import java.util.concurrent.TimeUnit

data class ProcessResult(val exitCode: Int, val stdout: String, val stderr: String)

/** Subprocess seam. Injected in tests so the CLI can be a local stub. */
interface ProcessRunner {
    fun run(
        argv: List<String>,
        env: Map<String, String>,
        workingDir: File?,
        stdin: String?,
        timeoutMs: Long,
    ): ProcessResult

    /** Line-oriented streaming (NDJSON). The returned sequence is lazy and blocking. */
    fun stream(
        argv: List<String>,
        env: Map<String, String>,
        workingDir: File?,
    ): Sequence<String>
}

/** Default runner backed by java.lang.ProcessBuilder. */
class DefaultProcessRunner : ProcessRunner {

    override fun run(
        argv: List<String>,
        env: Map<String, String>,
        workingDir: File?,
        stdin: String?,
        timeoutMs: Long,
    ): ProcessResult {
        val pb = ProcessBuilder(argv)
        if (workingDir != null) pb.directory(workingDir)
        pb.environment().putAll(env)
        val process = try {
            pb.start()
        } catch (e: Exception) {
            throw DarkmoonClientException("Failed to launch darkmoon-ci: ${argv.firstOrNull()}", e)
        }

        if (stdin != null) {
            process.outputStream.use { it.write(stdin.toByteArray(Charsets.UTF_8)) }
        } else {
            process.outputStream.close()
        }

        // Read both streams concurrently to avoid pipe deadlock.
        val stdout = StringBuilder()
        val stderr = StringBuilder()
        val tOut = Thread { process.inputStream.bufferedReader().use { stdout.append(it.readText()) } }
        val tErr = Thread { process.errorStream.bufferedReader().use { stderr.append(it.readText()) } }
        tOut.start(); tErr.start()

        val finished = process.waitFor(timeoutMs, TimeUnit.MILLISECONDS)
        if (!finished) {
            process.destroyForcibly()
            throw DarkmoonClientException("darkmoon-ci timed out after ${timeoutMs}ms")
        }
        tOut.join(2000); tErr.join(2000)
        return ProcessResult(process.exitValue(), stdout.toString(), stderr.toString())
    }

    override fun stream(
        argv: List<String>,
        env: Map<String, String>,
        workingDir: File?,
    ): Sequence<String> = sequence {
        val pb = ProcessBuilder(argv)
        if (workingDir != null) pb.directory(workingDir)
        pb.environment().putAll(env)
        pb.redirectErrorStream(false)
        val process = try {
            pb.start()
        } catch (e: Exception) {
            throw DarkmoonClientException("Failed to launch darkmoon-ci stream", e)
        }
        process.outputStream.close()
        val reader: BufferedReader = process.inputStream.bufferedReader()
        try {
            while (true) {
                val line = reader.readLine() ?: break
                if (line.isNotBlank()) yield(line)
            }
        } finally {
            reader.close()
            process.destroy()
        }
    }
}
