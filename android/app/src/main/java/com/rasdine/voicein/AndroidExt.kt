package com.rasdine.voicein

import android.content.Context

internal fun Context.dp(value: Int): Int =
    (value * resources.displayMetrics.density + 0.5f).toInt()
