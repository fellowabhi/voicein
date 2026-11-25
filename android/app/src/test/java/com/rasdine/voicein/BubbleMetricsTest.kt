package com.rasdine.voicein

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class BubbleMetricsTest {
    @Test
    fun defaultSizeIsSmallerThanTheFirstReleaseAndStillATapTarget() {
        assertEquals(48, BubbleMetrics.SIZE_DEFAULT_DP)
        assertTrue(BubbleMetrics.SIZE_DEFAULT_DP >= 48)
        assertTrue(BubbleMetrics.SIZE_MIN_DP >= 40)
        assertEquals(40, BubbleMetrics.sizeDp(1))
        assertEquals(96, BubbleMetrics.sizeDp(400))
        assertEquals(48, BubbleMetrics.sizeDp(48))
    }

    @Test
    fun opacityStaysVisibleAndRecordingPullsItTowardSolid() {
        assertEquals(35, BubbleMetrics.opacityPercent(0))
        assertEquals(100, BubbleMetrics.opacityPercent(140))
        assertEquals(0.35f, BubbleMetrics.shownOpacity(35, 0f), 0.001f)
        assertEquals(1f, BubbleMetrics.shownOpacity(100, 0.6f), 0.001f)
        val recording = BubbleMetrics.shownOpacity(35, 0.6f)
        assertTrue(recording > 0.35f)
        assertTrue(recording < 1f)
    }

    @Test
    fun idleWindowAlphaMatchesTheSliderSoTheOverlayCanFade() {
        assertEquals(1f, BubbleMetrics.windowAlpha(100, BubbleState.IDLE), 0.001f)
        assertEquals(0.35f, BubbleMetrics.windowAlpha(35, BubbleState.IDLE), 0.001f)
        assertEquals(0.5f, BubbleMetrics.windowAlpha(50, BubbleState.IDLE), 0.001f)
        val recording = BubbleMetrics.windowAlpha(35, BubbleState.RECORDING)
        assertTrue(recording > BubbleMetrics.windowAlpha(35, BubbleState.IDLE))
        assertTrue(recording < 1f)
        assertEquals(1f, BubbleMetrics.windowAlpha(100, BubbleState.RECORDING), 0.001f)
    }
}