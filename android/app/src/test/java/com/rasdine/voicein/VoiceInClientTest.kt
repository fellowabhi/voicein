package com.rasdine.voicein

import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InputStream
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.Locale
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

/**
 * Locks the bytes the bubble sends to the checks in voicein/web.py:
 * form login, session cookie from the 303, then raw audio with Origin,
 * X-VoiceIn, and the cookie. The redirect to `/` must not be followed.
 *
 * Uses a socket instead of com.sun.net.httpserver, which the Android unit-test
 * classpath does not include.
 */
class VoiceInClientTest {
    private lateinit var loop: Loopback
    private val seen = AtomicReference<Captured>()

    @Before
    fun setUp() {
        seen.set(null)
        loop = Loopback { request ->
            when (request.path) {
                "/login" -> login(request)
                "/transcribe" -> transcribe(request)
                "/" -> {
                    loop.homeHits.incrementAndGet()
                    Reply(200, "OK", emptyList(), "<html>app</html>".toByteArray())
                }
                else -> Reply(404, "Not Found", emptyList(), ByteArray(0))
            }
        }
    }

    @After
    fun tearDown() {
        loop.stop()
    }

    @Test
    fun loginTakesTheCookieAndDoesNotFollowTheRedirect() {
        val cookie = client().login("correct-horse")
        assertEquals(TOKEN, cookie)
        assertEquals(0, loop.homeHits.get())
    }

    @Test
    fun wrongPasswordIsUnauthorized() {
        try {
            client().login("nope")
            fail("expected sign-in failure")
        } catch (e: SignInException) {
            assertEquals("Wrong password.", e.message)
        }
    }

    @Test
    fun transcribeMatchesTheWebPageRequest() {
        client().transcribe(AUDIO, TOKEN)
        val shot = seen.get()
        assertEquals(loop.origin, shot.origin)
        assertEquals("1", shot.token)
        assertEquals("voicein_auth=$TOKEN", shot.cookie)
        assertTrue(shot.type!!.startsWith("audio/mp4"))
        assertArrayEquals(AUDIO, shot.body)
        assertEquals(0, loop.homeHits.get())
    }

    @Test
    fun expiredSessionAsksForSignIn() {
        try {
            client().transcribe(AUDIO, "stale")
            fail("expected auth failure")
        } catch (e: TranscribeException) {
            assertTrue(e.signInAgain)
            assertEquals("Sign in first.", e.message)
        }
    }

    @Test
    fun emptyRecordingIsRejectedLocally() {
        try {
            client().transcribe(ByteArray(0), TOKEN)
            fail("expected local rejection")
        } catch (e: TranscribeException) {
            assertEquals("Recording was empty.", e.message)
        }
        assertNull(seen.get())
    }

    private fun client() = VoiceInClient(VoiceInProtocol.endpoint(loop.origin))

    private fun login(request: RawRequest): Reply {
        if (request.header("Origin") != loop.origin) return json(403, """{"error":"Bad origin"}""")
        if (request.body.toString(Charsets.UTF_8) != "password=correct-horse") {
            return Reply(401, "Unauthorized", emptyList(), ByteArray(0))
        }
        return Reply(
            303,
            "See Other",
            listOf(
                "Location" to "${loop.origin}/",
                "Set-Cookie" to "voicein_auth=$TOKEN; HttpOnly; Path=/; SameSite=Strict; Max-Age=100; Secure",
            ),
            ByteArray(0),
        )
    }

    private fun transcribe(request: RawRequest): Reply {
        val shot = Captured(
            origin = request.header("Origin"),
            token = request.header("X-VoiceIn"),
            cookie = request.header("Cookie"),
            type = request.header("Content-Type"),
            body = request.body,
        )
        seen.set(shot)
        return when {
            shot.origin != loop.origin -> json(403, """{"error":"Bad origin"}""")
            shot.token != "1" -> json(403, """{"error":"Missing request token."}""")
            shot.cookie != "voicein_auth=$TOKEN" -> json(401, """{"error":"Sign in first."}""")
            shot.type == null || !shot.type.contains("mp4") -> json(400, """{"error":"bad type"}""")
            !shot.body.contentEquals(AUDIO) -> json(400, """{"ok": false, "error": "wrong bytes"}""")
            else -> json(200, """{"ok": true}""")
        }
    }

    private fun json(code: Int, body: String): Reply {
        val reason = if (code == 200) "OK" else "Error"
        return Reply(
            code,
            reason,
            listOf("Content-Type" to "application/json; charset=utf-8"),
            body.toByteArray(Charsets.UTF_8),
        )
    }

    private class Loopback(private val handler: (RawRequest) -> Reply) {
        private val server = ServerSocket(0, 16, InetAddress.getByName("127.0.0.1"))
        val origin = "http://127.0.0.1:${server.localPort}"
        val homeHits = AtomicInteger()
        private val thread = Thread {
            while (!server.isClosed) {
                val socket = try {
                    server.accept()
                } catch (_: IOException) {
                    break
                }
                socket.soTimeout = 5_000
                try {
                    val request = readRequest(socket.getInputStream())
                    val reply = handler(request)
                    writeReply(socket, reply)
                } catch (_: IOException) {
                    // The client closed early, or the assertion server stopped.
                } finally {
                    try {
                        socket.close()
                    } catch (_: IOException) {
                    }
                }
            }
        }.apply {
            isDaemon = true
            name = "voicein-test-http"
            start()
        }

        fun stop() {
            try {
                server.close()
            } catch (_: IOException) {
            }
            thread.join(1_000)
        }
    }

    private data class Captured(
        val origin: String?,
        val token: String?,
        val cookie: String?,
        val type: String?,
        val body: ByteArray,
    )

    companion object {
        private const val TOKEN = "1700000000.abc.def"
        private val AUDIO = byteArrayOf(1, 2, 3, 4, 5, 6, 7, 8)

        private fun readRequest(input: InputStream): RawRequest {
            val header = ByteArrayOutputStream()
            while (true) {
                val b = input.read()
                if (b == -1) break
                header.write(b)
                val size = header.size()
                if (size >= 4) {
                    val raw = header.toByteArray()
                    if (raw[size - 4] == '\r'.code.toByte() &&
                        raw[size - 3] == '\n'.code.toByte() &&
                        raw[size - 2] == '\r'.code.toByte() &&
                        raw[size - 1] == '\n'.code.toByte()
                    ) {
                        break
                    }
                }
                if (size > 64 * 1024) error("request headers too large")
            }
            val text = header.toString(Charsets.ISO_8859_1.name())
            val lines = text.substringBefore("\r\n\r\n").split("\r\n")
            val requestLine = lines.first().split(" ")
            val path = requestLine.getOrElse(1) { "/" }
            val headers = linkedMapOf<String, String>()
            for (line in lines.drop(1)) {
                val eq = line.indexOf(':')
                if (eq <= 0) continue
                headers[line.substring(0, eq).trim().lowercase(Locale.US)] = line.substring(eq + 1).trim()
            }
            val length = headers["content-length"]?.toIntOrNull() ?: 0
            val body = ByteArray(length)
            var read = 0
            while (read < length) {
                val n = input.read(body, read, length - read)
                if (n < 0) break
                read += n
            }
            return RawRequest(path, headers, if (read == length) body else body.copyOf(read))
        }

        private fun writeReply(socket: Socket, reply: Reply) {
            val head = buildString {
                append("HTTP/1.1 ${reply.code} ${reply.reason}\r\n")
                for ((name, value) in reply.headers) append("$name: $value\r\n")
                append("Content-Length: ${reply.body.size}\r\n")
                append("Connection: close\r\n\r\n")
            }
            val out = socket.getOutputStream()
            out.write(head.toByteArray(Charsets.ISO_8859_1))
            out.write(reply.body)
            out.flush()
        }
    }
}

private data class RawRequest(
    val path: String,
    val headers: Map<String, String>,
    val body: ByteArray,
) {
    fun header(name: String): String? = headers[name.lowercase(Locale.US)]
}

private data class Reply(
    val code: Int,
    val reason: String,
    val headers: List<Pair<String, String>>,
    val body: ByteArray,
)
