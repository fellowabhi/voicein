package com.rasdine.voicein

import android.content.Context
import android.content.SharedPreferences

/** Server URL, session cookie, and bubble position. The password is never written. */
internal class SessionStore(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    var serverUrl: String
        get() = prefs.getString(KEY_URL, VoiceInProtocol.DEFAULT_SERVER) ?: VoiceInProtocol.DEFAULT_SERVER
        set(value) {
            prefs.edit().putString(KEY_URL, value).commit()
        }

    var cookie: String?
        get() = prefs.getString(KEY_COOKIE, null)?.takeIf { it.isNotEmpty() }
        set(value) {
            val editor = prefs.edit()
            if (value.isNullOrEmpty()) editor.remove(KEY_COOKIE) else editor.putString(KEY_COOKIE, value)
            editor.commit()
        }

    var haptics: Boolean
        get() = prefs.getBoolean(KEY_HAPTICS, true)
        set(value) {
            prefs.edit().putBoolean(KEY_HAPTICS, value).apply()
        }

    var bubbleSizeDp: Int
        get() = BubbleMetrics.sizeDp(prefs.getInt(KEY_BUBBLE_SIZE, BubbleMetrics.SIZE_DEFAULT_DP))
        set(value) {
            prefs.edit().putInt(KEY_BUBBLE_SIZE, BubbleMetrics.sizeDp(value)).apply()
        }

    var bubbleOpacityPercent: Int
        get() = BubbleMetrics.opacityPercent(prefs.getInt(KEY_BUBBLE_OPACITY, BubbleMetrics.OPACITY_DEFAULT))
        set(value) {
            prefs.edit().putInt(KEY_BUBBLE_OPACITY, BubbleMetrics.opacityPercent(value)).apply()
        }

    fun watchAppearance(listener: SharedPreferences.OnSharedPreferenceChangeListener) {
        prefs.registerOnSharedPreferenceChangeListener(listener)
    }

    fun unwatchAppearance(listener: SharedPreferences.OnSharedPreferenceChangeListener) {
        prefs.unregisterOnSharedPreferenceChangeListener(listener)
    }

    fun bubblePosition(): Pair<Int, Int>? {
        if (!prefs.contains(KEY_X) || !prefs.contains(KEY_Y)) return null
        return prefs.getInt(KEY_X, 0) to prefs.getInt(KEY_Y, 0)
    }

    fun saveBubblePosition(x: Int, y: Int) {
        prefs.edit().putInt(KEY_X, x).putInt(KEY_Y, y).apply()
    }

    internal companion object {
        const val PREFS = "voicein"
        const val KEY_URL = "server_url"
        const val KEY_COOKIE = "cookie"
        const val KEY_HAPTICS = "haptics"
        const val KEY_X = "bubble_x"
        const val KEY_Y = "bubble_y"
        const val KEY_BUBBLE_SIZE = "bubble_size_dp"
        const val KEY_BUBBLE_OPACITY = "bubble_opacity"
    }
}
