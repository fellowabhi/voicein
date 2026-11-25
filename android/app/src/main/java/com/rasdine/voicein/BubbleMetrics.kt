package com.rasdine.voicein

/** Bubble size in dp and opacity percent. Kept free of Android types so tests can pin the ranges. */
internal object BubbleMetrics {
    const val SIZE_MIN_DP = 40
    const val SIZE_MAX_DP = 96
    const val SIZE_DEFAULT_DP = 48

    const val OPACITY_MIN = 35
    const val OPACITY_MAX = 100
    const val OPACITY_DEFAULT = 100

    fun sizeDp(raw: Int): Int = raw.coerceIn(SIZE_MIN_DP, SIZE_MAX_DP)

    fun opacityPercent(raw: Int): Int = raw.coerceIn(OPACITY_MIN, OPACITY_MAX)

    /**
     * User opacity is 0..1. [lift] pulls a faint bubble toward solid (0 = unchanged, 1 = fully opaque)
     * so recording stays readable without ignoring the slider.
     */
    fun shownOpacity(userPercent: Int, lift: Float): Float {
        val user = opacityPercent(userPercent) / 100f
        val clamped = lift.coerceIn(0f, 1f)
        return user + (1f - user) * clamped
    }

    /**
     * Alpha for [android.view.WindowManager.LayoutParams.alpha].
     * Idle uses the slider as-is. Recording lifts toward solid.
     */
    fun windowAlpha(opacityPercent: Int, state: BubbleState): Float {
        val lift = when (state) {
            BubbleState.RECORDING -> 0.6f
            BubbleState.UPLOADING, BubbleState.SUCCESS, BubbleState.ERROR -> 0.4f
            BubbleState.IDLE -> 0f
        }
        return shownOpacity(opacityPercent, lift)
    }
}
