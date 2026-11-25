package com.rasdine.voicein

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.inputmethod.EditorInfo
import android.widget.TextView
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.widget.doAfterTextChanged
import com.google.android.material.button.MaterialButton
import com.google.android.material.switchmaterial.SwitchMaterial
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {
    private val store by lazy { SessionStore(this) }
    private val io = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "voicein-login").apply { isDaemon = true }
    }
    private var notifResolved = false
    private var signingIn = false

    private lateinit var serverLayout: TextInputLayout
    private lateinit var serverUrl: TextInputEditText
    private lateinit var passwordLayout: TextInputLayout
    private lateinit var password: TextInputEditText
    private lateinit var signIn: MaterialButton
    private lateinit var showBubble: MaterialButton
    private lateinit var hideBubble: MaterialButton
    private lateinit var signOut: MaterialButton
    private lateinit var haptics: SwitchMaterial
    private lateinit var permissions: TextView
    private lateinit var sessionNote: TextView
    private lateinit var status: TextView

    private val askMic = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) {
            onShowClick()
        } else {
            setStatus(getString(R.string.mic_denied), error = true)
        }
        render()
    }

    private val askNotif = registerForActivityResult(ActivityResultContracts.RequestPermission()) {
        notifResolved = true
        onShowClick()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContentView(R.layout.activity_main)
        bind()
        applyInsets()
        serverUrl.setText(store.serverUrl)
        haptics.isChecked = store.haptics
        haptics.setOnCheckedChangeListener { _, checked -> store.haptics = checked }
        password.doAfterTextChanged { if (!signingIn) signIn.isEnabled = !it.isNullOrEmpty() }
        password.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_DONE && signIn.isEnabled) {
                signIn()
                true
            } else {
                false
            }
        }
        signIn.setOnClickListener { signIn() }
        showBubble.setOnClickListener { onShowClick() }
        hideBubble.setOnClickListener { hideBubble() }
        signOut.setOnClickListener { signOut() }
        signIn.isEnabled = false
        render()
        if (store.cookie.isNullOrEmpty()) {
            setStatus(getString(R.string.session_note), error = false)
        }
    }

    override fun onResume() {
        super.onResume()
        render()
    }

    override fun onDestroy() {
        io.shutdown()
        super.onDestroy()
    }

    private fun bind() {
        serverLayout = findViewById(R.id.serverLayout)
        serverUrl = findViewById(R.id.serverUrl)
        passwordLayout = findViewById(R.id.passwordLayout)
        password = findViewById(R.id.password)
        signIn = findViewById(R.id.signIn)
        showBubble = findViewById(R.id.showBubble)
        hideBubble = findViewById(R.id.hideBubble)
        signOut = findViewById(R.id.signOut)
        haptics = findViewById(R.id.haptics)
        permissions = findViewById(R.id.permissions)
        sessionNote = findViewById(R.id.sessionNote)
        status = findViewById(R.id.status)
    }

    private fun applyInsets() {
        val content = findViewById<android.view.View>(R.id.content)
        val start = content.paddingLeft
        val top = content.paddingTop
        val end = content.paddingRight
        val bottom = content.paddingBottom
        ViewCompat.setOnApplyWindowInsetsListener(content) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime())
            view.setPadding(start + bars.left, top + bars.top, end + bars.right, bottom + bars.bottom)
            insets
        }
    }

    private fun render() {
        val signedIn = !store.cookie.isNullOrEmpty()
        passwordLayout.visibility = if (signedIn) android.view.View.GONE else android.view.View.VISIBLE
        signIn.visibility = if (signedIn) android.view.View.GONE else android.view.View.VISIBLE
        sessionNote.visibility = if (signedIn) android.view.View.VISIBLE else android.view.View.GONE
        permissions.visibility = if (signedIn) android.view.View.VISIBLE else android.view.View.GONE
        showBubble.visibility = if (signedIn) android.view.View.VISIBLE else android.view.View.GONE
        hideBubble.visibility = if (signedIn) android.view.View.VISIBLE else android.view.View.GONE
        haptics.visibility = if (signedIn) android.view.View.VISIBLE else android.view.View.GONE
        signOut.visibility = if (signedIn) android.view.View.VISIBLE else android.view.View.GONE
        serverLayout.isEnabled = !signedIn
        if (signedIn) {
            permissions.text = permissionLines()
            showBubble.text = when {
                !micGranted() -> getString(R.string.allow_mic)
                !Settings.canDrawOverlays(this) -> getString(R.string.allow_overlay)
                else -> getString(R.string.show_bubble)
            }
            if (haptics.isChecked != store.haptics) haptics.isChecked = store.haptics
        }
    }

    private fun signIn() {
        if (signingIn) return
        val typedUrl = serverUrl.text?.toString().orEmpty()
        val typedPassword = password.text?.toString().orEmpty()
        if (typedPassword.isEmpty()) return
        val endpoint = try {
            VoiceInProtocol.endpoint(typedUrl)
        } catch (e: IllegalArgumentException) {
            setStatus(e.message ?: getString(R.string.server_url), error = true)
            return
        }
        signingIn = true
        signIn.isEnabled = false
        setStatus(getString(R.string.signing_in), error = false)
        io.execute {
            val result = runCatching { VoiceInClient(endpoint).login(typedPassword) }
            runOnUiThread {
                signingIn = false
                result.onSuccess { cookie ->
                    store.serverUrl = endpoint.base
                    store.cookie = cookie
                }
                if (isDestroyed) return@runOnUiThread
                result.onSuccess {
                    serverUrl.setText(endpoint.base)
                    password.setText("")
                }
                signIn.isEnabled = !password.text.isNullOrEmpty()
                result.fold(
                    onSuccess = {
                        setStatus(getString(R.string.signed_in_ready), error = false)
                        render()
                    },
                    onFailure = { error ->
                        setStatus(error.message ?: getString(R.string.signing_in), error = true)
                    },
                )
            }
        }
    }

    private fun signOut() {
        val cookie = store.cookie
        val url = store.serverUrl
        store.cookie = null
        hideBubble()
        password.setText("")
        render()
        setStatus(getString(R.string.session_note), error = false)
        if (cookie.isNullOrEmpty()) return
        io.execute {
            runCatching {
                VoiceInClient(VoiceInProtocol.endpoint(url)).logout(cookie)
            }
        }
    }

    private fun onShowClick() {
        if (!micGranted()) {
            askMic.launch(Manifest.permission.RECORD_AUDIO)
            return
        }
        if (Build.VERSION.SDK_INT >= 33 &&
            !notifResolved &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            askNotif.launch(Manifest.permission.POST_NOTIFICATIONS)
            return
        }
        if (!Settings.canDrawOverlays(this)) {
            setStatus(getString(R.string.overlay_needed), error = true)
            startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
            return
        }
        ContextCompat.startForegroundService(this, Intent(this, BubbleService::class.java))
        setStatus(getString(R.string.bubble_shown), error = false)
    }

    private fun hideBubble() {
        if (!BubbleService.active) return
        startService(Intent(this, BubbleService::class.java).setAction(BubbleService.ACTION_HIDE))
        setStatus(getString(R.string.bubble_hidden), error = false)
    }

    private fun permissionLines(): String {
        fun line(name: String, ok: Boolean): String {
            val state = if (ok) getString(R.string.allowed) else getString(R.string.needed)
            return "$name — $state"
        }
        val notifOk = Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        return listOf(
            line(getString(R.string.perm_mic), micGranted()),
            line(getString(R.string.perm_notif), notifOk),
            line(getString(R.string.perm_overlay), Settings.canDrawOverlays(this)),
        ).joinToString("\n")
    }

    private fun micGranted(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun setStatus(text: CharSequence, error: Boolean) {
        status.text = text
        status.setTextColor(ContextCompat.getColor(this, if (error) R.color.danger else R.color.muted))
    }
}
