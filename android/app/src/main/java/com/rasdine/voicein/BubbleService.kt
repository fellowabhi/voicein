package com.rasdine.voicein

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.ComponentCallbacks
import android.content.Intent
import android.content.pm.ServiceInfo
import android.content.res.Configuration
import android.graphics.PixelFormat
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.provider.Settings
import android.util.Log
import android.view.Gravity
import android.view.WindowManager
import android.widget.Toast
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import java.util.concurrent.Executors
import kotlin.math.abs

/**
 * Floating bubble and the microphone foreground service.
 *
 * The service is microphone-typed the whole time it is up, so a tap can open
 * the mic while another app is in front. Android allows that only from a
 * foreground service that already has the microphone type.
 */
class BubbleService : Service(), BubbleView.Listener {
    private val main = Handler(Looper.getMainLooper())
    private val io = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "voicein-upload")
    }
    private val configCallback = object : ComponentCallbacks {
        override fun onConfigurationChanged(newConfig: Configuration) {
            if (bubble?.isAttachedToWindow == true) snap()
        }

        override fun onLowMemory() = Unit
    }

    private lateinit var windowManager: WindowManager
    private lateinit var store: SessionStore
    private lateinit var params: WindowManager.LayoutParams
    private var bubble: BubbleView? = null
    private var dismiss: DismissTargetView? = null
    private var recorder: MicRecorder? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var state = BubbleState.IDLE
    private var detailText = ""
    private var busy = false
    private var pendingHide = false
    private var destroyed = false
    private var epoch = 0
    private var dragStartX = 0
    private var dragStartY = 0

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        active = true
        store = SessionStore(this)
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        detailText = getString(R.string.notif_idle)
        createChannel()
        registerComponentCallbacks(configCallback)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startInForeground()
        if (!Settings.canDrawOverlays(this)) {
            stopCompletely()
            return START_NOT_STICKY
        }
        return when (intent?.action) {
            ACTION_HIDE -> {
                hide()
                if (pendingHide) START_STICKY else START_NOT_STICKY
            }
            ACTION_TOGGLE -> {
                showBubble()
                toggle()
                START_STICKY
            }
            else -> {
                showBubble()
                START_STICKY
            }
        }
    }

    override fun onDestroy() {
        destroyed = true
        active = false
        main.removeCallbacksAndMessages(null)
        removeBubble()
        removeDismiss()
        recorder?.discard()
        recorder = null
        releaseWake()
        unregisterComponentCallbacks(configCallback)
        io.shutdown()
        super.onDestroy()
    }

    override fun onTap() = toggle()

    override fun onLongPress() {
        haptic()
        hide()
    }

    override fun onDragStart() {
        dragStartX = params.x
        dragStartY = params.y
        showDismiss()
    }

    override fun onDrag(dx: Int, dy: Int) {
        moveTo(dragStartX + dx, dragStartY + dy)
    }

    override fun onDragEnd() {
        if (overDismiss()) {
            hide()
        } else {
            removeDismiss()
            snap()
        }
    }

    private fun toggle() {
        if (pendingHide || busy) return
        if (recorder?.isRecording == true) stopAndUpload() else startRecording()
    }

    @SuppressLint("MissingPermission")
    private fun startRecording() {
        if (ContextCompat.checkSelfPermission(this, android.Manifest.permission.RECORD_AUDIO)
            != android.content.pm.PackageManager.PERMISSION_GRANTED
        ) {
            fail(getString(R.string.mic_needed))
            return
        }
        val rec = MicRecorder(this)
        try {
            rec.start()
        } catch (e: Exception) {
            Log.w(TAG, "Microphone start failed", e)
            fail(getString(R.string.mic_failed))
            return
        }
        recorder = rec
        setState(BubbleState.RECORDING, getString(R.string.notif_recording))
        haptic()
        main.removeCallbacks(maxDuration)
        main.postDelayed(maxDuration, MAX_RECORDING_MS)
    }

    private fun stopAndUpload() {
        if (busy) return
        val rec = recorder ?: return
        recorder = null
        main.removeCallbacks(maxDuration)
        busy = true
        val bytes = try {
            rec.stop()
        } catch (e: Exception) {
            busy = false
            fail(e.message ?: getString(R.string.mic_failed))
            return
        }
        haptic()
        if (bytes.isEmpty()) {
            busy = false
            fail("Recording was too short.")
            return
        }
        val cookie = store.cookie
        val url = store.serverUrl
        if (cookie.isNullOrEmpty()) {
            busy = false
            fail("Sign in again.")
            return
        }
        setState(BubbleState.UPLOADING, getString(R.string.notif_uploading))
        acquireWake()
        io.execute {
            val result = runCatching {
                val endpoint = VoiceInProtocol.endpoint(url)
                VoiceInClient(endpoint).transcribe(bytes, cookie)
            }
            main.post {
                if (destroyed) return@post
                busy = false
                releaseWake()
                result.fold(
                    onSuccess = { succeed() },
                    onFailure = { error ->
                        if (error is TranscribeException && error.signInAgain) store.cookie = null
                        Log.w(TAG, "Upload failed", error)
                        fail(error.message ?: "Network error. Try again.")
                    },
                )
            }
        }
    }

    private fun succeed() {
        if (destroyed) return
        val message = getString(R.string.notif_success)
        setState(BubbleState.SUCCESS, message)
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
        if (pendingHide) stopCompletely() else flashIdle()
    }

    private fun fail(message: String) {
        if (destroyed) return
        setState(BubbleState.ERROR, message)
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
        if (pendingHide) stopCompletely() else flashIdle()
    }

    private fun flashIdle() {
        val token = epoch
        val delay = if (state == BubbleState.ERROR) 3500L else 1600L
        main.postDelayed({
            if (destroyed || token != epoch) return@postDelayed
            if (state == BubbleState.SUCCESS || state == BubbleState.ERROR) {
                setState(BubbleState.IDLE, getString(R.string.notif_idle))
            }
        }, delay)
    }

    private val maxDuration = Runnable {
        if (recorder?.isRecording == true) stopAndUpload()
    }

    private fun hide() {
        if (recorder?.isRecording == true) {
            recorder?.discard()
            recorder = null
            main.removeCallbacks(maxDuration)
        }
        removeBubble()
        removeDismiss()
        if (busy) {
            pendingHide = true
            publish()
            return
        }
        stopCompletely()
    }

    private fun stopCompletely() {
        pendingHide = false
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun showBubble() {
        if (bubble?.isAttachedToWindow == true) {
            bubble?.state = state
            return
        }
        val view = BubbleView(this)
        view.listener = this
        view.state = state
        params = overlayParams(WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.WRAP_CONTENT)
        placeInitially()
        try {
            windowManager.addView(view, params)
        } catch (e: RuntimeException) {
            Log.w(TAG, "Could not add the bubble", e)
            stopCompletely()
            return
        }
        bubble = view
        view.post { if (view.isAttachedToWindow) snap() }
    }

    private fun placeInitially() {
        val screen = screen()
        val size = dp(72)
        val margin = dp(8)
        val saved = store.bubblePosition()
        if (saved != null) {
            params.x = saved.first
            params.y = saved.second
        } else {
            params.x = screen.first - size - margin
            params.y = screen.second / 3
        }
    }

    private fun moveTo(x: Int, y: Int) {
        val screen = screen()
        val w = bubble?.width?.takeIf { it > 0 } ?: dp(72)
        val h = bubble?.height?.takeIf { it > 0 } ?: dp(72)
        params.x = x.coerceIn(0, (screen.first - w).coerceAtLeast(0))
        params.y = y.coerceIn(0, (screen.second - h).coerceAtLeast(0))
        val view = bubble ?: return
        if (view.isAttachedToWindow) windowManager.updateViewLayout(view, params)
        updateDismissArmed()
    }

    private fun snap() {
        val view = bubble ?: return
        if (!view.isAttachedToWindow) return
        val screen = screen()
        val w = view.width.takeIf { it > 0 } ?: dp(72)
        val h = view.height.takeIf { it > 0 } ?: dp(72)
        val margin = dp(8)
        val mid = params.x + w / 2
        params.x = if (mid < screen.first / 2) margin else (screen.first - w - margin).coerceAtLeast(margin)
        val maxY = (screen.second - h - margin).coerceAtLeast(margin)
        params.y = params.y.coerceIn(margin, maxY)
        windowManager.updateViewLayout(view, params)
        store.saveBubblePosition(params.x, params.y)
    }

    private fun showDismiss() {
        if (dismiss?.isAttachedToWindow == true) return
        val size = dp(64)
        val view = DismissTargetView(this)
        val layout = overlayParams(size, size).apply {
            flags = flags or WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
            gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            y = dp(56)
        }
        try {
            windowManager.addView(view, layout)
        } catch (e: RuntimeException) {
            Log.w(TAG, "Could not show the hide target", e)
            return
        }
        dismiss = view
        view.alpha = 0f
        view.animate().alpha(1f).setDuration(120).start()
        updateDismissArmed()
    }

    private fun updateDismissArmed() {
        dismiss?.armed = overDismiss()
    }

    private fun overDismiss(): Boolean {
        val w = bubble?.width?.takeIf { it > 0 } ?: dp(72)
        val h = bubble?.height?.takeIf { it > 0 } ?: dp(72)
        val bx = params.x + w / 2
        val by = params.y + h / 2
        val screen = screen()
        val size = dp(64)
        val dx = bx - screen.first / 2
        val dy = by - (screen.second - dp(56) - size / 2)
        val reach = dp(96)
        return abs(dx) < reach && abs(dy) < reach && dx * dx + dy * dy < reach * reach
    }

    private fun removeBubble() {
        val view = bubble ?: return
        bubble = null
        removeView(view)
    }

    private fun removeDismiss() {
        val view = dismiss ?: return
        dismiss = null
        removeView(view)
    }

    private fun removeView(view: android.view.View) {
        try {
            if (view.isAttachedToWindow) windowManager.removeView(view)
        } catch (_: RuntimeException) {
            // Already gone, or removed from inside its own touch dispatch.
        }
    }

    private fun overlayParams(width: Int, height: Int): WindowManager.LayoutParams {
        return WindowManager.LayoutParams(
            width,
            height,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.LEFT
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS
            } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
            }
        }
    }

    @Suppress("DEPRECATION")
    private fun screen(): Pair<Int, Int> {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val bounds = windowManager.currentWindowMetrics.bounds
            bounds.width() to bounds.height()
        } else {
            val display = windowManager.defaultDisplay
            val metrics = android.util.DisplayMetrics()
            display.getRealMetrics(metrics)
            metrics.widthPixels to metrics.heightPixels
        }
    }

    private fun setState(next: BubbleState, detail: String) {
        epoch++
        state = next
        detailText = detail
        bubble?.state = next
        publish()
    }

    private fun startInForeground() {
        val notification = buildNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            startForeground(NOTIF_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } else {
            startForeground(NOTIF_ID, notification)
        }
    }

    private fun publish() {
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIF_ID, buildNotification())
    }

    private fun buildNotification(): Notification {
        val open = PendingIntent.getActivity(
            this,
            1,
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_mic)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(detailText)
            .setContentIntent(open)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .setColor(0xFF2D6DFF.toInt())
        if (!pendingHide && state != BubbleState.UPLOADING) {
            val label = if (state == BubbleState.RECORDING) R.string.action_stop else R.string.action_record
            val icon = if (state == BubbleState.RECORDING) R.drawable.ic_close else R.drawable.ic_mic
            builder.addAction(icon, getString(label), pendingService(ACTION_TOGGLE, 2))
            builder.addAction(R.drawable.ic_close, getString(R.string.action_hide), pendingService(ACTION_HIDE, 3))
        }
        return builder.build()
    }

    private fun pendingService(action: String, requestCode: Int): PendingIntent {
        val intent = Intent(this, BubbleService::class.java).setAction(action)
        return PendingIntent.getService(
            this,
            requestCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    private fun createChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.notif_channel),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = getString(R.string.notif_channel_desc)
            setShowBadge(false)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun haptic() {
        if (!store.haptics) return
        val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            (getSystemService(VIBRATOR_MANAGER_SERVICE) as VibratorManager).defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            getSystemService(VIBRATOR_SERVICE) as Vibrator
        }
        if (!vibrator.hasVibrator()) return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            vibrator.vibrate(VibrationEffect.createPredefined(VibrationEffect.EFFECT_CLICK))
        } else {
            vibrator.vibrate(VibrationEffect.createOneShot(20, VibrationEffect.DEFAULT_AMPLITUDE))
        }
    }

    private fun acquireWake() {
        val pm = getSystemService(POWER_SERVICE) as PowerManager
        val lock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "voicein:upload")
        lock.setReferenceCounted(false)
        lock.acquire(4 * 60 * 1000L)
        wakeLock = lock
    }

    private fun releaseWake() {
        val lock = wakeLock ?: return
        wakeLock = null
        try {
            if (lock.isHeld) lock.release()
        } catch (_: RuntimeException) {
            // Already released by the timeout.
        }
    }

    companion object {
        const val ACTION_TOGGLE = "com.rasdine.voicein.TOGGLE"
        const val ACTION_HIDE = "com.rasdine.voicein.HIDE"

        @Volatile
        var active: Boolean = false
            private set

        private const val TAG = "VoiceIn"
        private const val CHANNEL_ID = "voicein_bubble"
        private const val NOTIF_ID = 1001
        private const val MAX_RECORDING_MS = 5 * 60 * 1000L
    }
}
