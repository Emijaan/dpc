package com.akdevicelock.dpc.status

import android.app.Activity
import android.app.ActivityManager
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import com.akdevicelock.dpc.BuildConfig
import com.akdevicelock.dpc.commands.AppState
import com.akdevicelock.dpc.commands.CommandPollService
import com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver
import com.akdevicelock.dpc.enrollment.Enrollment
import com.akdevicelock.dpc.lock.DevicePolicyLockManager
import com.akdevicelock.dpc.lock.KioskRestrictionManager
import com.akdevicelock.dpc.lock.LockResult
import java.text.DateFormat
import java.util.Date

class MainActivity : Activity() {

    private val handler = Handler(Looper.getMainLooper())
    private var renderedKey = ""
    private val refresh = object : Runnable {
        override fun run() { render(); handler.postDelayed(this, 2000) }
    }
    private val pad get() = (24 * resources.displayMetrics.density).toInt()

    override fun onResume() {
        super.onResume()
        renderedKey = ""
        if (AppState(this).isRegistered) CommandPollService.start(this)
        handler.post(refresh)
    }

    override fun onPause() {
        super.onPause()
        handler.removeCallbacks(refresh)
    }

    private fun lockTaskState(): Int =
        (getSystemService(ACTIVITY_SERVICE) as ActivityManager).lockTaskModeState

    /** Re-evaluates what to show; only rebuilds the UI when the underlying state changed. */
    private fun render() {
        val kiosk = KioskRestrictionManager(this)
        val state = AppState(this)
        val restricted = kiosk.isApplied() && kiosk.isSupported()
        val key = "$restricted|${state.isRegistered}|${state.lastSync}|${state.connection}|${state.lastCommand}"
        if (key == renderedKey) return
        renderedKey = key
        if (restricted) {
            showRestricted(state)
            if (lockTaskState() == ActivityManager.LOCK_TASK_MODE_NONE) {
                try { startLockTask() } catch (_: Exception) {}
            }
        } else {
            if (lockTaskState() != ActivityManager.LOCK_TASK_MODE_NONE) {
                try { stopLockTask() } catch (_: Exception) {}
            }
            showStatus(state)
        }
    }

    private fun root() = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(pad, pad, pad, pad)
        gravity = Gravity.CENTER_HORIZONTAL
    }

    private fun fmt(t: Long) =
        if (t == 0L) "never" else DateFormat.getDateTimeInstance().format(Date(t))

    private fun showStatus(state: AppState) {
        val root = root()
        root.addView(TextView(this).apply { text = "AK DeviceLock"; textSize = 28f })
        val owner = AkDeviceAdminReceiver.isDeviceOwner(this)
        root.addView(TextView(this).apply {
            textSize = 15f
            setPadding(0, pad / 2, 0, pad / 2)
            text = """
                Device Owner: ${if (owner) "YES" else "NO"}
                Device: ${Build.MANUFACTURER} ${Build.MODEL}
                Android: ${Build.VERSION.RELEASE} (SDK ${Build.VERSION.SDK_INT})
                App version: ${BuildConfig.VERSION_NAME}
                Registration: ${if (state.isRegistered) "registered" else "not registered"}
                Connection: ${state.connection}
                Management: ${if (owner) "managed" else "unmanaged"}
                Restriction: none
                Last sync: ${fmt(state.lastSync)}
                Last command: ${state.lastCommand}
            """.trimIndent()
        })
        val result = TextView(this)
        if (!state.isRegistered) {
            val url = EditText(this).apply { hint = "Server URL (e.g. http://192.168.1.34:8000)"; setText(state.serverUrl) }
            val key = EditText(this).apply { hint = "Enrollment key" }
            root.addView(url); root.addView(key)
            root.addView(Button(this).apply {
                text = "Register device"
                setOnClickListener {
                    result.text = "Registering..."
                    Thread {
                        val err = Enrollment.register(this@MainActivity, url.text.toString(), key.text.toString())
                        runOnUiThread {
                            if (err == null) { CommandPollService.start(this@MainActivity); renderedKey = ""; render() }
                            else result.text = err
                        }
                    }.start()
                }
            })
        }
        root.addView(Button(this).apply {
            text = "Test lockNow() (local)"
            setOnClickListener {
                result.text = when (val r = DevicePolicyLockManager(this@MainActivity).lock()) {
                    is LockResult.Success -> "lockNow() called"
                    is LockResult.Failure -> "Failed: ${r.reason}"
                }
            }
        })
        root.addView(Button(this).apply {
            text = "Apply kiosk restriction (local test)"
            setOnClickListener {
                val r = KioskRestrictionManager(this@MainActivity).lock()
                if (r is LockResult.Failure) result.text = "Failed: ${r.reason}"
            }
        })
        root.addView(result)
        setContentView(android.widget.ScrollView(this).apply { addView(root) })
    }

    private fun showRestricted(state: AppState) {
        val root = root().apply { gravity = Gravity.CENTER }
        root.addView(TextView(this).apply {
            text = "AK DeviceLock"; textSize = 28f
            if (BuildConfig.DEBUG) {
                // Debug builds only: long-press to release during development testing.
                setOnLongClickListener {
                    KioskRestrictionManager(this@MainActivity).unlock()
                    try { stopLockTask() } catch (_: Exception) {}
                    renderedKey = ""
                    render()
                    true
                }
            }
        })
        root.addView(TextView(this).apply {
            text = "This device is currently restricted.\n\nPlease contact support to restore access."
            textSize = 18f
            gravity = Gravity.CENTER
            setPadding(0, pad, 0, pad)
        })
        root.addView(TextView(this).apply {
            text = "Last sync: ${fmt(state.lastSync)}"
            gravity = Gravity.CENTER
        })
        root.addView(Button(this).apply {
            text = "Emergency call"
            setOnClickListener { startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:112"))) }
        })
        setContentView(root)
    }

    @Deprecated("Back is disabled while restricted")
    override fun onBackPressed() {
        if (!KioskRestrictionManager(this).isApplied()) super.onBackPressed()
    }
}
