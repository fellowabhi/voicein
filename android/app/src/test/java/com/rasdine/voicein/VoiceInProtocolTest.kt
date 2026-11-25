package com.rasdine.voicein

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

class VoiceInProtocolTest {
    @Test
    fun defaultServerOrigin() {
        val endpoint = VoiceInProtocol.endpoint("https://voice.rasdine.com")
        assertEquals("https://voice.rasdine.com", endpoint.base)
        assertEquals("https://voice.rasdine.com", endpoint.origin)
    }

    @Test
    fun addsHttpsAndDropsDefaultPortAndSlash() {
        assertEquals("https://voice.rasdine.com", VoiceInProtocol.endpoint("voice.rasdine.com").origin)
        assertEquals("https://voice.rasdine.com", VoiceInProtocol.endpoint("HTTPS://Voice.Rasdine.com:443/").origin)
        assertEquals("http://127.0.0.1:8765", VoiceInProtocol.endpoint("http://127.0.0.1:8765").origin)
    }

    @Test
    fun rejectsAnythingButTheSiteRoot() {
        assertInvalid("ftp://voice.rasdine.com")
        assertInvalid("https://voice.rasdine.com/transcribe")
        assertInvalid("https://user:pw@voice.rasdine.com")
        assertInvalid("https://voice.rasdine.com/?x=1")
        assertInvalid("")
    }

    @Test
    fun formBodyMatchesParseQs() {
        assertEquals("password=a%26b%3Dc+d", VoiceInProtocol.formBody("a&b=c d"))
        assertEquals("password=", VoiceInProtocol.formBody(""))
    }

    @Test
    fun readsVoiceInCookieAndIgnoresAttributes() {
        val token = "1700000000.abc.def"
        val headers = listOf(
            "other=1; Path=/",
            "voicein_auth=$token; HttpOnly; Path=/; SameSite=Strict; Max-Age=7776000; Secure",
        )
        assertEquals(token, VoiceInProtocol.authCookie(headers))
        assertEquals("voicein_auth=$token", VoiceInProtocol.cookieHeader(token))
        assertNull(VoiceInProtocol.authCookie(listOf("voicein_auth=; Max-Age=0")))
        assertNull(VoiceInProtocol.authCookie(emptyList()))
    }

    @Test
    fun parsesTranscribeJson() {
        assertEquals(true, FlatJson.parse("""{"ok": true}""")["ok"])
        val failed = FlatJson.parse("""{"ok": false, "error": "Transcription contained no usable text"}""")
        assertEquals(false, failed["ok"])
        assertEquals("Transcription contained no usable text", failed["error"])
        assertEquals("Say \"hi\"", FlatJson.parse("""{"error": "Say \"hi\""}""")["error"])
        assertEquals("café", FlatJson.parse("""{"error": "caf\u00e9"}""")["error"])
        assertTrue(FlatJson.parse("").isEmpty())
    }

    private fun assertInvalid(raw: String) {
        try {
            VoiceInProtocol.endpoint(raw)
            fail("expected rejection of $raw")
        } catch (_: IllegalArgumentException) {
            // The message is shown on the sign-in screen.
        }
    }
}
