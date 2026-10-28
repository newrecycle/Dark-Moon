package fr.ascit.darkmoon.client

import java.io.BufferedReader
import java.io.InputStream
import java.util.Timer
import java.util.TimerTask
import java.util.concurrent.atomic.AtomicBoolean
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
class DefaultProcessRunner(private val streamTimeoutMs: Long = 60_000) : ProcessRunner {

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
            throw DarkmoonClientException("The configured darkmoon-ci process could not be started")
        }

        val expired = AtomicBoolean(false)
        val failedRead = AtomicBoolean(false)
        val timer = Timer(true)
        timer.schedule(object : TimerTask() {
            override fun run() { expired.set(true); terminate(process) }
        }, timeoutMs.coerceAtLeast(1))
        val stdout = StringBuilder()
        val stderr = StringBuilder()
        fun drain(stream: InputStream, output: StringBuilder) = Thread {
            try {
                stream.bufferedReader().use { reader ->
                    val buffer = CharArray(4096)
                    while (true) {
                        val count = reader.read(buffer)
                        if (count < 0) break
                        if (output.length + count > 8 * 1024 * 1024) {
                            failedRead.set(true); terminate(process); break
                        }
                        output.append(buffer, 0, count)
                    }
                }
            } catch (_: Exception) { failedRead.set(true) }
        }.apply { isDaemon = true; start() }
        val tOut = drain(process.inputStream, stdout)
        val tErr = drain(process.errorStream, stderr)
        try {
            process.outputStream.use { if (stdin != null) it.write(stdin.toByteArray(Charsets.UTF_8)) }
            if (!process.waitFor(timeoutMs.coerceAtLeast(1), TimeUnit.MILLISECONDS) || expired.get()) {
                throw DarkmoonClientException("darkmoon-ci timed out; completion is unverified")
            }
            tOut.join(2000); tErr.join(2000)
            if (expired.get() || failedRead.get() || tOut.isAlive || tErr.isAlive) throw DarkmoonClientException("darkmoon-ci output is incomplete or exceeds the size limit")
            return ProcessResult(process.exitValue(), stdout.toString(), stderr.toString())
        } catch (_: InterruptedException) {
            Thread.currentThread().interrupt()
            throw DarkmoonClientException("darkmoon-ci was interrupted; completion is unverified")
        } catch (error: DarkmoonClientException) {
            throw error
        } catch (_: Exception) {
            throw DarkmoonClientException("darkmoon-ci transport failed; response contents are withheld")
        } finally {
            timer.cancel()
            terminate(process)
            runCatching { process.inputStream.close() }
            runCatching { process.errorStream.close() }
            runCatching { process.outputStream.close() }
        }
    }

    private fun terminate(process: Process) {
        process.descendants().forEach { it.destroyForcibly() }
        process.destroyForcibly()
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
            throw DarkmoonClientException("The configured progress process could not be started")
        }
        process.outputStream.close()
        val expired = AtomicBoolean(false)
        val timer = Timer(true)
        // Sequence iteration can be abandoned without a close callback. The
        // watchdog bounds that child lifetime even if the consumer never resumes.
        timer.schedule(object : TimerTask() {
            override fun run() { expired.set(true); terminate(process) }
        }, streamTimeoutMs.coerceAtLeast(1))
        val errors = Thread {
            runCatching { process.errorStream.use { stream ->
                val buffer = ByteArray(4096)
                while (stream.read(buffer) >= 0) { /* drain without retaining raw errors */ }
            } }
        }.apply { isDaemon = true; start() }
        val reader: BufferedReader = process.inputStream.bufferedReader()
        try {
            while (true) {
                val line = StringBuilder()
                var ended = false
                while (true) {
                    val value = reader.read()
                    if (value < 0) { ended = true; break }
                    if (value == 10) break
                    if (line.length >= 1024 * 1024) throw DarkmoonClientException("Progress event exceeds the size limit")
                    if (value != 13) line.append(value.toChar())
                }
                if (expired.get()) throw DarkmoonClientException("Progress stream timed out")
                if (line.isNotBlank()) yield(line.toString())
                if (ended) break
            }
            if (!process.waitFor(1000, TimeUnit.MILLISECONDS) || expired.get()) throw DarkmoonClientException("Progress stream did not finish within its deadline")
            if (process.exitValue() != 0) throw DarkmoonClientException("Progress subprocess failed; output is withheld")
        } catch (error: DarkmoonClientException) {
            throw error
        } catch (_: Exception) {
            throw DarkmoonClientException("Progress transport failed; completion is unverified")
        } finally {
            timer.cancel()
            terminate(process)
            runCatching { reader.close() }
            runCatching { process.errorStream.close() }
            errors.join(1000)
        }
    }
}
