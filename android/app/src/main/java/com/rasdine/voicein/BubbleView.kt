package com.rasdine.voicein

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.drawable.Drawable
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.animation.LinearInterpolator
import androidx.core.content.ContextCompat
import kotlin.math.hypot

internal enum class BubbleState {
    IDLE,
    RECORDING,
    UPLOADING,
    SUCCESS,
    ERROR,
}

internal class BubbleView(context: Context) : View(context) {
    interface Listener {
        fun onTap()
        fun onLongPress()
        fun onDragStart()
        fun onDrag(dx: Int, dy: Int)
        fun onDragEnd()
    }

    var listener: Listener? = null

    var state: BubbleState = BubbleState.IDLE
        set(value) {
            if (field == value) return
            field = value
            contentDescription = descriptionFor(value)
            when (value) {
                BubbleState.RECORDING -> {
                    stopSpin()
                    startPulse()
                }
                BubbleState.UPLOADING -> {
                    stopPulse()
                    startSpin()
                }
                else -> {
                    stopPulse()
                    stopSpin()
                }
            }
            invalidate()
        }

    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        color = Color.WHITE
    }
    private val mic: Drawable = ContextCompat.getDrawable(context, R.drawable.ic_mic)!!.mutate()
    private val slop = ViewConfiguration.get(context).scaledTouchSlop
    private val arc = RectF()
    private val longPress = Runnable {
        if (dragging) return@Runnable
        longPressed = true
        listener?.onLongPress()
    }

    private var pulse = 0f
    private var spin = 0f
    private var pulseAnim: ValueAnimator? = null
    private var spinAnim: ValueAnimator? = null
    private var downRawX = 0f
    private var downRawY = 0f
    private var dragging = false
    private var longPressed = false

    init {
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        contentDescription = descriptionFor(BubbleState.IDLE)
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val size = context.dp(72)
        setMeasuredDimension(size, size)
    }

    override fun onDraw(canvas: Canvas) {
        val cx = width / 2f
        val cy = height / 2f
        val radius = width / 2f - context.dp(6)
        val color = colorFor(state)

        if (state == BubbleState.RECORDING) {
            fill.color = color
            fill.alpha = (70 + 80 * (1f - pulse)).toInt()
            canvas.drawCircle(cx, cy, radius + context.dp(4) * pulse, fill)
        }

        fill.alpha = 255
        fill.color = color
        canvas.drawCircle(cx, cy, radius, fill)

        if (state == BubbleState.UPLOADING) {
            val r = radius * 0.42f
            arc.set(cx - r, cy - r, cx + r, cy + r)
            stroke.strokeWidth = context.dp(3).toFloat()
            canvas.drawArc(arc, spin, 110f, false, stroke)
            return
        }
        when (state) {
            BubbleState.RECORDING -> drawStop(canvas, cx, cy, radius)
            BubbleState.SUCCESS -> drawCheck(canvas, cx, cy, radius)
            BubbleState.ERROR -> drawBang(canvas, cx, cy, radius)
            else -> drawMic(canvas, cx, cy, radius)
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                downRawX = event.rawX
                downRawY = event.rawY
                dragging = false
                longPressed = false
                removeCallbacks(longPress)
                postDelayed(longPress, 500L)
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                val dx = event.rawX - downRawX
                val dy = event.rawY - downRawY
                if (!dragging && hypot(dx.toDouble(), dy.toDouble()) > slop) {
                    dragging = true
                    removeCallbacks(longPress)
                    listener?.onDragStart()
                }
                if (dragging) listener?.onDrag(dx.toInt(), dy.toInt())
                return true
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                removeCallbacks(longPress)
                if (longPressed) return true
                if (dragging) {
                    if (event.actionMasked == MotionEvent.ACTION_UP) listener?.onDragEnd()
                } else if (event.actionMasked == MotionEvent.ACTION_UP) {
                    listener?.onTap()
                }
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    override fun onDetachedFromWindow() {
        removeCallbacks(longPress)
        stopPulse()
        stopSpin()
        super.onDetachedFromWindow()
    }

    private fun drawMic(canvas: Canvas, cx: Float, cy: Float, radius: Float) {
        val half = (radius * 0.48f).toInt()
        mic.setBounds((cx - half).toInt(), (cy - half).toInt(), (cx + half).toInt(), (cy + half).toInt())
        mic.draw(canvas)
    }

    private fun drawStop(canvas: Canvas, cx: Float, cy: Float, radius: Float) {
        val half = radius * 0.22f
        fill.color = Color.WHITE
        canvas.drawRoundRect(cx - half, cy - half, cx + half, cy + half, 6f, 6f, fill)
    }

    private fun drawCheck(canvas: Canvas, cx: Float, cy: Float, radius: Float) {
        stroke.strokeWidth = context.dp(3).toFloat()
        val s = radius * 0.28f
        canvas.drawLine(cx - s, cy, cx - s * 0.25f, cy + s * 0.7f, stroke)
        canvas.drawLine(cx - s * 0.25f, cy + s * 0.7f, cx + s, cy - s * 0.55f, stroke)
    }

    private fun drawBang(canvas: Canvas, cx: Float, cy: Float, radius: Float) {
        stroke.strokeWidth = context.dp(3).toFloat()
        canvas.drawLine(cx, cy - radius * 0.28f, cx, cy + radius * 0.05f, stroke)
        fill.color = Color.WHITE
        canvas.drawCircle(cx, cy + radius * 0.28f, context.dp(2).toFloat(), fill)
    }

    private fun startPulse() {
        if (pulseAnim != null) return
        pulseAnim = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 700
            repeatMode = ValueAnimator.REVERSE
            repeatCount = ValueAnimator.INFINITE
            addUpdateListener {
                pulse = it.animatedValue as Float
                invalidate()
            }
            start()
        }
    }

    private fun stopPulse() {
        pulseAnim?.cancel()
        pulseAnim = null
        pulse = 0f
    }

    private fun startSpin() {
        if (spinAnim != null) return
        spinAnim = ValueAnimator.ofFloat(0f, 360f).apply {
            duration = 800
            repeatCount = ValueAnimator.INFINITE
            interpolator = LinearInterpolator()
            addUpdateListener {
                spin = it.animatedValue as Float
                invalidate()
            }
            start()
        }
    }

    private fun stopSpin() {
        spinAnim?.cancel()
        spinAnim = null
        spin = 0f
    }

    private fun colorFor(value: BubbleState): Int = when (value) {
        BubbleState.IDLE -> 0xFF2D6DFF.toInt()
        BubbleState.RECORDING -> 0xFFD32F2F.toInt()
        BubbleState.UPLOADING -> 0xFFE6A23C.toInt()
        BubbleState.SUCCESS -> 0xFF2E7D32.toInt()
        BubbleState.ERROR -> 0xFFB71C1C.toInt()
    }

    private fun descriptionFor(value: BubbleState): String = when (value) {
        BubbleState.IDLE -> context.getString(R.string.bubble_cd_idle)
        BubbleState.RECORDING -> context.getString(R.string.bubble_cd_recording)
        BubbleState.UPLOADING -> context.getString(R.string.bubble_cd_uploading)
        BubbleState.SUCCESS -> context.getString(R.string.bubble_cd_success)
        BubbleState.ERROR -> context.getString(R.string.bubble_cd_error)
    }
}

internal class DismissTargetView(context: Context) : View(context) {
    var armed: Boolean = false
        set(value) {
            if (field == value) return
            field = value
            invalidate()
        }

    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
    }

    init {
        contentDescription = context.getString(R.string.dismiss_cd)
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO
    }

    override fun onDraw(canvas: Canvas) {
        val cx = width / 2f
        val cy = height / 2f
        val radius = width / 2f - context.dp(2)
        fill.color = if (armed) 0xFFE53935.toInt() else 0xE61B1E24.toInt()
        canvas.drawCircle(cx, cy, radius, fill)
        stroke.strokeWidth = context.dp(2).toFloat()
        val d = radius * 0.32f
        canvas.drawLine(cx - d, cy - d, cx + d, cy + d, stroke)
        canvas.drawLine(cx - d, cy + d, cx + d, cy - d, stroke)
    }
}
