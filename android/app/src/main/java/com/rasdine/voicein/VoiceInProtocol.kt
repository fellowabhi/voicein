package com.rasdine.voicein

import java.net.URI
import java.net.URISyntaxException
import java.net.URLEncoder

/**
 * Header and cookie contract shared with the phone page in `voicein/web.py`.
 *
 * The server accepts a POST only when Host and Origin (or Referer) are its
 * public host, `localhost`, or `127.0.0.1`. A native client is not a browser,
 * so it sends `Origin` itself, set to the configured server. Login may omit
 * Origin; transcribe may not. The session value is the `voicein_auth` cookie.
 */
internal object VoiceInProtocol {
    const val DEFAULT_SERVER = "https://voice.rasdine.com"
    const val COOKIE_NAME = "voicein_auth"
    const val CLIENT_HEADER = "X-VoiceIn"
    const val CLIENT_HEADER_VALUE = "1"
    const val AUDIO_CONTENT_TYPE = "audio/mp4"
    const val USER_AGENT = "VoiceInAndroid/0.1"
    const val MAX_AUDIO_BYTES = 20 * 1024 * 1024

    data class Endpoint(val base: String, val origin: String)

    fun endpoint(raw: String): Endpoint {
        val trimmed = raw.trim()
        require(trimmed.isNotEmpty()) { "Enter the server URL." }
        val withScheme = if ("://" in trimmed) trimmed else "https://$trimmed"
        val uri = try {
            URI(withScheme)
        } catch (_: URISyntaxException) {
            throw IllegalArgumentException("Server URL is not valid.")
        }
        val scheme = uri.scheme?.lowercase()
        require(scheme == "https" || scheme == "http") {
            "Server URL must start with https:// or http://."
        }
        val host = uri.host?.lowercase()?.trim()
        require(!host.isNullOrEmpty()) { "Server URL needs a host." }
        require(uri.userInfo == null) { "Remove the username from the server URL." }
        require(uri.rawQuery == null && uri.rawFragment == null) {
            "Use the site root, without a ?query or #fragment."
        }
        val path = uri.rawPath ?: ""
        require(path.isEmpty() || path == "/") {
            "Use the site root, for example https://voice.rasdine.com."
        }
        val omitPort = uri.port == -1 ||
            (scheme == "https" && uri.port == 443) ||
            (scheme == "http" && uri.port == 80)
        val port = if (omitPort) "" else ":${uri.port}"
        val hostText = if (host.contains(':') && !host.startsWith("[")) "[$host]" else host
        val origin = "$scheme://$hostText$port"
        return Endpoint(base = origin, origin = origin)
    }

    fun formBody(password: String): String =
        "password=" + URLEncoder.encode(password, Charsets.UTF_8.name())

    fun cookieHeader(token: String): String = "$COOKIE_NAME=$token"

    /** Pull `voicein_auth` out of one or more `Set-Cookie` header values. */
    fun authCookie(setCookieHeaders: List<String>?): String? {
        if (setCookieHeaders.isNullOrEmpty()) return null
        for (header in setCookieHeaders) {
            val pair = header.substringBefore(';').trim()
            val eq = pair.indexOf('=')
            if (eq <= 0) continue
            val name = pair.substring(0, eq).trim()
            val value = pair.substring(eq + 1).trim()
            if (name == COOKIE_NAME && value.isNotEmpty()) return value
        }
        return null
    }
}

/** Flat JSON objects of the shape the transcribe endpoint returns. */
internal object FlatJson {
    fun parse(raw: String): Map<String, Any?> {
        val s = raw.trim()
        if (s.isEmpty()) return emptyMap()
        var i = 0

        fun skipWs() {
            while (i < s.length && s[i].isWhitespace()) i++
        }

        fun parseString(): String {
            check(i < s.length && s[i] == '"') { "bad json" }
            i++
            val out = StringBuilder()
            while (i < s.length) {
                val c = s[i++]
                if (c == '"') return out.toString()
                if (c != '\\') {
                    out.append(c)
                    continue
                }
                check(i < s.length) { "bad json" }
                when (val esc = s[i++]) {
                    '"', '\\', '/' -> out.append(esc)
                    'b' -> out.append('\b')
                    'f' -> out.append('\u000C')
                    'n' -> out.append('\n')
                    'r' -> out.append('\r')
                    't' -> out.append('\t')
                    'u' -> {
                        check(i + 4 <= s.length) { "bad json" }
                        out.append(s.substring(i, i + 4).toInt(16).toChar())
                        i += 4
                    }
                    else -> out.append(esc)
                }
            }
            error("bad json")
        }

        fun literal(word: String, value: Any?): Any? {
            check(s.startsWith(word, i)) { "bad json" }
            i += word.length
            return value
        }

        fun parseValue(): Any? {
            check(i < s.length) { "bad json" }
            return when (s[i]) {
                '"' -> parseString()
                't' -> literal("true", true)
                'f' -> literal("false", false)
                'n' -> literal("null", null)
                else -> {
                    val start = i
                    while (i < s.length && s[i] != ',' && s[i] != '}') i++
                    s.substring(start, i).trim()
                }
            }
        }

        check(s[i] == '{') { "bad json" }
        i++
        val out = linkedMapOf<String, Any?>()
        while (true) {
            skipWs()
            check(i < s.length) { "bad json" }
            if (s[i] == '}') return out
            if (s[i] == ',') {
                i++
                continue
            }
            val key = parseString()
            skipWs()
            check(i < s.length && s[i] == ':') { "bad json" }
            i++
            skipWs()
            out[key] = parseValue()
        }
    }
}
