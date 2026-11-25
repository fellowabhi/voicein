package com.rasdine.voicein

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException
import java.util.concurrent.TimeUnit

internal open class VoiceInException(message: String, cause: Throwable? = null) : Exception(message, cause)

internal class SignInException(message: String, cause: Throwable? = null) : VoiceInException(message, cause)

internal class TranscribeException(
    message: String,
    val signInAgain: Boolean = false,
    cause: Throwable? = null,
) : VoiceInException(message, cause)

/**
 * Phone recorder routes, matching voicein/web_pages.py.
 *
 * `POST /login` is form-encoded. The session token is the `voicein_auth` value
 * on the 303 `Set-Cookie`; the redirect to `/` is not followed. `POST /transcribe`
 * is the raw recording plus `X-VoiceIn: 1`, that cookie, and `Origin` set to the
 * server URL. The laptop pastes. The body is `{"ok": true}` or `{"error": "..."}`.
 */
internal class VoiceInClient(
    private val endpoint: VoiceInProtocol.Endpoint,
    private val http: OkHttpClient = shared,
) {
    fun login(password: String): String = guard(SignInKind) {
        val body = VoiceInProtocol.formBody(password)
            .toRequestBody(FORM.toMediaType())
        val request = base(LOGIN)
            .post(body)
            .build()
        http.newCall(request).execute().use { response ->
            val cookie = VoiceInProtocol.authCookie(response.headers("Set-Cookie"))
            val code = response.code
            if (!cookie.isNullOrEmpty() && code != 401 && code != 429 && code != 503) {
                cookie
            } else {
                val message = when (code) {
                    401 -> "Wrong password."
                    429 -> "Too many attempts. Wait 15 minutes."
                    503 -> "VoiceIn web auth is not set up on the server."
                    else -> "Sign-in failed ($code)."
                }
                throw SignInException(message)
            }
        }
    }

    fun logout(cookie: String) {
        val request = base(LOGOUT)
            .header("Cookie", VoiceInProtocol.cookieHeader(cookie))
            .post(ByteArray(0).toRequestBody(FORM.toMediaType()))
            .build()
        try {
            http.newCall(request).execute().close()
        } catch (_: IOException) {
            // The phone already dropped its copy. Logout only clears a browser cookie.
        }
    }

    fun transcribe(audio: ByteArray, cookie: String) = guard(TranscribeKind) {
        if (audio.isEmpty()) throw TranscribeException("Recording was empty.")
        if (audio.size > VoiceInProtocol.MAX_AUDIO_BYTES) {
            throw TranscribeException("Recording is too large.")
        }
        val request = base(TRANSCRIBE)
            .header(VoiceInProtocol.CLIENT_HEADER, VoiceInProtocol.CLIENT_HEADER_VALUE)
            .header("Cookie", VoiceInProtocol.cookieHeader(cookie))
            .header("Accept", "application/json")
            .post(audio.toRequestBody(VoiceInProtocol.AUDIO_CONTENT_TYPE.toMediaType()))
            .build()
        http.newCall(request).execute().use { response ->
            val parsed = parse(response)
            val ok = parsed["ok"] == true
            if (response.code == 401) {
                throw TranscribeException(serverMessage(parsed, response.code, "Sign in again."), signInAgain = true)
            }
            if (response.code !in 200..299 || !ok) {
                throw TranscribeException(serverMessage(parsed, response.code, "Transcription failed"))
            }
        }
    }

    private fun base(path: String): Request.Builder =
        Request.Builder()
            .url(endpoint.base + path)
            .header("Origin", endpoint.origin)
            .header("User-Agent", VoiceInProtocol.USER_AGENT)

    private fun parse(response: Response): Map<String, Any?> {
        val text = response.body?.string().orEmpty()
        return try {
            FlatJson.parse(text)
        } catch (_: IllegalStateException) {
            emptyMap()
        }
    }

    private fun serverMessage(parsed: Map<String, Any?>, code: Int, fallback: String): String {
        val error = (parsed["error"] as? String)?.trim().orEmpty()
        return error.ifEmpty { "$fallback ($code)." }
    }

    private inline fun <T> guard(kind: Kind, block: () -> T): T {
        try {
            return block()
        } catch (e: VoiceInException) {
            throw e
        } catch (e: IOException) {
            throw kind.network(e)
        }
    }

    private sealed interface Kind {
        fun network(cause: IOException): VoiceInException
    }

    private data object SignInKind : Kind {
        override fun network(cause: IOException) = SignInException("Network error. Try again.", cause)
    }

    private data object TranscribeKind : Kind {
        override fun network(cause: IOException) = TranscribeException("Network error. Try again.", cause = cause)
    }

    companion object {
        private const val LOGIN = "/login"
        private const val LOGOUT = "/logout"
        private const val TRANSCRIBE = "/transcribe"
        private const val FORM = "application/x-www-form-urlencoded; charset=utf-8"

        val shared: OkHttpClient = OkHttpClient.Builder()
            .followRedirects(false)
            .followSslRedirects(false)
            .retryOnConnectionFailure(false)
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(180, TimeUnit.SECONDS)
            .writeTimeout(120, TimeUnit.SECONDS)
            .build()
    }
}
