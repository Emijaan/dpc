package com.akdevicelock.dpc.status

import android.app.Activity
import android.app.ActivityManager
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import com.akdevicelock.dpc.BuildConfig
import com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver
import com.akdevicelock.dpc.lock.DevicePolicyLockManager
import com.akdevicelock.dpc.lock.KioskRestrictionManager
import com.akdevicelock.dpc.lock.LockResult

class MainActivity : Activity() {

    private val pad get() = (24 * resources.displayMetrics.density).toInt()

    override fun onResume() {
        super.onResume()
        val kiosk = KioskRestrictionManager(this)
        if (kiosk.isApplied() && kiosk.isSupported()) {
            showRestricted()
            if (lockTaskState() == ActivityManager.LOCK_TASK_MODE_NONE) {
                try { startLockTask() } catch (_: Exception) {}
            }
        } else {
            if (lockTaskState() != ActivityManager.LOCK_TASK_MODE_NONE) {
                try { stopLockTask() } catch (_: Exception) {}
            }
            showStatus()
        }
    }

    private fun lockTaskState(): Int =
        (getSystemService(ACTIVITY_SERVICE) as ActivityManager).lockTaskModeState

    private fun root() = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(pad, pad, pad, pad)
        gravity = Gravity.CENTER_HORIZONTAL
    }

    private fun showStatus() {
        val root = root()
        root.addView(TextView(this).apply { text = "AK DeviceLock"; textSize = 28f })
        val owner = AkDeviceAdminReceiver.isDeviceOwner(this)
        root.addView(TextView(this).apply {
            textSize = 16f
            setPadding(0, pad, 0, pad)
            text = """
                Device Owner: ${if (owner) "YES" else "NO"}
                Manufacturer: ${Build.MANUFACTURER}
                Model: ${Build.MODEL}
                Android: ${Build.VERSION.RELEASE} (SDK ${Build.VERSION.SDK_INT})
                App version: ${BuildConfig.VERSION_NAME}
                Restriction: none
                Registration: not registered (backend not implemented yet)
            """.trimIndent()
        })
        val result = TextView(this).apply { setPadding(0, pad, 0, 0) }
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
        setContentView(root)
    }

    private fun showRestricted() {
        val root = root().apply { gravity = Gravity.CENTER }
        root.addView(TextView(this).apply {
            text = "AK DeviceLock"; textSize = 28f
            if (BuildConfig.DEBUG) {
                // Debug builds only: long-press to release during development testing.
                setOnLongClickListener {
                    KioskRestrictionManager(this@MainActivity).unlock()
                    try { stopLockTask() } catch (_: Exception) {}
                    showStatus()
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
        root.addView(Button(this).apply {
            text = "Emergency call"
            setOnClickListener {
                startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:112")))
            }
        })
        setContentView(root)
    }

    @Deprecated("Back is disabled while restricted")
    override fun onBackPressed() {
        if (!KioskRestrictionManager(this).isApplied()) super.onBackPressed()
    }
}
