package com.akdevicelock.dpc.status

import android.annotation.SuppressLint
import android.app.Activity
import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import com.akdevicelock.dpc.BuildConfig
import com.akdevicelock.dpc.R
import com.akdevicelock.dpc.commands.AppState
import com.akdevicelock.dpc.commands.CommandPollService
import com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver
import com.akdevicelock.dpc.enrollment.Enrollment
import com.akdevicelock.dpc.lock.DevicePolicyLockManager
import com.akdevicelock.dpc.lock.EnrollmentProtection
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

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    override fun onResume() {
        super.onResume()
        renderedKey = ""
        EnrollmentProtection.enforce(this)
        AkDeviceAdminReceiver.ensureDefaultsAndStart(this)
        if (AppState(this).isRegistered) CommandPollService.start(this)
        handler.post(refresh)
    }

    override fun onPause() {
        super.onPause()
        handler.removeCallbacks(refresh)
    }

    private fun lockTaskState(): Int =
        (getSystemService(ACTIVITY_SERVICE) as ActivityManager).lockTaskModeState

    private fun isBatteryExempt(): Boolean {
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        return pm.isIgnoringBatteryOptimizations(packageName)
    }

    private fun render() {
        val kiosk = KioskRestrictionManager(this)
        val state = AppState(this)
        val restricted = kiosk.isApplied() && kiosk.isSupported()
        val owner = AkDeviceAdminReceiver.isDeviceOwner(this)
        val batt = isBatteryExempt()
        val key = "$restricted|$owner|$batt|${state.isRegistered}|${state.lastSync}|${state.connection}|${state.lastCommand}"
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
            showStatus(state, owner, batt)
        }
    }

    private fun cardBg(fillHex: String, strokeHex: String, radiusDp: Int = 14): GradientDrawable =
        GradientDrawable().apply {
            setColor(Color.parseColor(fillHex))
            setStroke(dp(1), Color.parseColor(strokeHex))
            cornerRadius = dp(radiusDp).toFloat()
        }

    private fun pillBg(fillHex: String, radiusDp: Int = 20): GradientDrawable =
        GradientDrawable().apply {
            setColor(Color.parseColor(fillHex))
            cornerRadius = dp(radiusDp).toFloat()
        }

    private fun styledButton(label: String, bgHex: String, textHex: String = "#FFFFFF", onClick: () -> Unit): Button =
        Button(this).apply {
            text = label
            isAllCaps = false
            setTextColor(Color.parseColor(textHex))
            textSize = 14f
            typeface = Typeface.DEFAULT_BOLD
            background = pillBg(bgHex, 10)
            setPadding(dp(14), dp(10), dp(14), dp(10))
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(8) }
            layoutParams = lp
            setOnClickListener { onClick() }
        }

    private fun fmt(t: Long) =
        if (t == 0L) "Never" else DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.MEDIUM).format(Date(t))

    @SuppressLint("BatteryLife")
    private fun showStatus(state: AppState, owner: Boolean, batteryExempt: Boolean) {
        val page = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(22), dp(18), dp(22))
            setBackgroundColor(Color.parseColor("#0A0F1D"))
        }

        // Brand Header Card
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = cardBg("#131C33", "#2563EB", 16)
            setPadding(dp(18), dp(18), dp(18), dp(18))
        }
        header.addView(TextView(this).apply {
            text = "🛡️ AK DeviceLock"
            textSize = 24f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#F8FAFC"))
        })
        header.addView(TextView(this).apply {
            text = "Enterprise Device Policy Controller • v${BuildConfig.VERSION_NAME}"
            textSize = 13f
            setTextColor(Color.parseColor("#94A3B8"))
            setPadding(0, dp(4), 0, dp(10))
        })
        val badgeText = when {
            owner && state.isRegistered -> "● ACTIVE & PROTECTED"
            owner -> "● DEVICE OWNER (REGISTERING...)"
            else -> "● AWAITING OWNERSHIP"
        }
        val badgeColor = when {
            owner && state.isRegistered -> "#059669"
            owner -> "#D97706"
            else -> "#DC2626"
        }
        header.addView(TextView(this).apply {
            text = badgeText
            textSize = 12f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.WHITE)
            background = pillBg(badgeColor, 16)
            setPadding(dp(12), dp(5), dp(12), dp(5))
        })
        page.addView(header)

        // Protection & Telemetry Card
        val resetBlocked = EnrollmentProtection.isFactoryResetBlocked(this)
        val adbBlocked = EnrollmentProtection.isUsbDebuggingBlocked(this)
        val infoCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = cardBg("#111827", "#1F2937", 14)
            setPadding(dp(16), dp(14), dp(16), dp(14))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(12) }
        }
        infoCard.addView(TextView(this).apply {
            text = "SECURITY & TELEMETRY"
            textSize = 12f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#60A5FA"))
            setPadding(0, 0, 0, dp(6))
        })
        infoCard.addView(TextView(this).apply {
            textSize = 14f
            setTextColor(Color.parseColor("#E2E8F0"))
            setLineSpacing(dp(3).toFloat(), 1f)
            text = """
                Device Owner: ${if (owner) "YES (Full Managed)" else "NO (Transfer or QR required)"}
                Factory Reset & OEM Unlock: ${if (resetBlocked) "BLOCKED" else "Not blocked"}
                USB Debugging & File Transfer: ${if (adbBlocked) "BLOCKED (Anti-Flash)" else if (owner) "USB Data Blocked" else "Not blocked"}
                App Uninstall: ${if (owner) "BLOCKED (Protected)" else "Not blocked"}
                Registration: ${if (state.isRegistered) "REGISTERED" else "NOT REGISTERED"}
                Connection: ${state.connection.uppercase()}
                Device Model: ${Build.MANUFACTURER} ${Build.MODEL} (Android ${Build.VERSION.RELEASE})
                Enrollment ID: ${state.installationId}
                Last Sync: ${fmt(state.lastSync)}
                Last Command: ${state.lastCommand}
            """.trimIndent()
        })
        page.addView(infoCard)

        // Permissions / Battery Optimization Card
        if (!batteryExempt) {
            val permCard = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                background = cardBg("#1E1B4B", "#4F46E5", 14)
                setPadding(dp(16), dp(14), dp(16), dp(14))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply { topMargin = dp(12) }
            }
            permCard.addView(TextView(this).apply {
                text = "BACKGROUND PROTECTION"
                textSize = 12f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(Color.parseColor("#A5B4FC"))
            })
            permCard.addView(TextView(this).apply {
                text = "Allow unrestricted battery usage so instant lock/unlock works 24/7."
                textSize = 13f
                setTextColor(Color.parseColor("#E0E7FF"))
                setPadding(0, dp(4), 0, dp(4))
            })
            permCard.addView(styledButton("Allow Background Battery Permission", "#4F46E5") {
                try {
                    startActivity(
                        Intent(
                            Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                            Uri.parse("package:$packageName")
                        )
                    )
                } catch (_: Exception) {}
            })
            page.addView(permCard)
        }

        val result = TextView(this).apply {
            setTextColor(Color.parseColor("#FBBF24"))
            textSize = 13f
            setPadding(0, dp(8), 0, 0)
        }

        // Enrollment Card (if not yet registered)
        if (!state.isRegistered) {
            val regCard = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                background = cardBg("#111827", "#374151", 14)
                setPadding(dp(16), dp(14), dp(16), dp(14))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply { topMargin = dp(12) }
            }
            regCard.addView(TextView(this).apply {
                text = "SERVER ACTIVATION"
                textSize = 12f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(Color.parseColor("#60A5FA"))
            })
            val defaultUrl = state.serverUrl.ifBlank { getString(R.string.default_server_url) }
            val defaultKey = state.pendingEnrollmentKey.ifBlank { getString(R.string.default_enrollment_key) }
            val urlInput = EditText(this).apply {
                hint = "Server URL"
                setText(defaultUrl)
                setTextColor(Color.WHITE)
                setHintTextColor(Color.parseColor("#64748B"))
            }
            val keyInput = EditText(this).apply {
                hint = "Enrollment Key"
                setText(defaultKey)
                setTextColor(Color.WHITE)
                setHintTextColor(Color.parseColor("#64748B"))
            }
            regCard.addView(urlInput)
            regCard.addView(keyInput)
            regCard.addView(styledButton("Activate & Register Now", "#2563EB") {
                result.text = "Registering with server..."
                Thread {
                    val err = Enrollment.register(this@MainActivity, urlInput.text.toString(), keyInput.text.toString())
                    runOnUiThread {
                        if (err == null) {
                            CommandPollService.syncNow(this@MainActivity)
                            renderedKey = ""
                            render()
                        } else {
                            result.text = err
                        }
                    }
                }.start()
            })
            page.addView(regCard)
        } else {
            page.addView(styledButton("Sync with Server Now", "#2563EB") {
                CommandPollService.syncNow(this@MainActivity)
                Toast.makeText(this@MainActivity, "Syncing with server...", Toast.LENGTH_SHORT).show()
            })
        }

        // Local Diagnostics Card
        val diagCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = cardBg("#111827", "#1F2937", 14)
            setPadding(dp(16), dp(14), dp(16), dp(14))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(12) }
        }
        diagCard.addView(TextView(this).apply {
            text = "DIAGNOSTIC CONTROLS"
            textSize = 12f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#94A3B8"))
        })
        diagCard.addView(styledButton("Test Immediate Screen Lock (lockNow)", "#334155") {
            result.text = when (val r = DevicePolicyLockManager(this@MainActivity).lock()) {
                is LockResult.Success -> "lockNow() executed"
                is LockResult.Failure -> "Failed: ${r.reason}"
            }
        })
        diagCard.addView(styledButton("Test Persistent Lock Screen (Kiosk)", "#475569") {
            val r = KioskRestrictionManager(this@MainActivity).lock()
            if (r is LockResult.Failure) result.text = "Failed: ${r.reason}"
        })
        diagCard.addView(result)
        page.addView(diagCard)

        setContentView(ScrollView(this).apply {
            setBackgroundColor(Color.parseColor("#0A0F1D"))
            addView(page)
        })
    }

    private fun showRestricted(state: AppState) {
        val page = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(20), dp(28), dp(20), dp(24))
            setBackgroundColor(Color.parseColor("#070B14"))
        }

        // Top Red/Indigo Security Shield Banner
        val banner = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            background = cardBg("#161F38", "#EF4444", 18)
            setPadding(dp(20), dp(22), dp(20), dp(22))
        }
        banner.addView(TextView(this).apply {
            text = "🔒"
            textSize = 42f
            gravity = Gravity.CENTER
            if (BuildConfig.DEBUG) {
                // Debug builds only: long-press lock icon to release during local testing
                setOnLongClickListener {
                    KioskRestrictionManager(this@MainActivity).unlock()
                    try { stopLockTask() } catch (_: Exception) {}
                    renderedKey = ""
                    render()
                    true
                }
            }
        })
        banner.addView(TextView(this).apply {
            text = "Your Phone Has Been Locked"
            textSize = 22f
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
            setTextColor(Color.parseColor("#F8FAFC"))
            setPadding(0, dp(8), 0, dp(4))
        })
        banner.addView(TextView(this).apply {
            text = "आपका फ़ोन लॉक कर दिया गया है"
            textSize = 17f
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
            setTextColor(Color.parseColor("#FCA5A5"))
        })
        banner.addView(TextView(this).apply {
            text = "This device is restricted under AK DeviceLock policy.\nईएमआई / एडमिन नीति के कारण यह फ़ोन लॉक किया गया है। अनलॉक करने के लिए अपने रिटेलर या सहायता केंद्र से संपर्क करें।"
            textSize = 13f
            gravity = Gravity.CENTER
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(0, dp(10), 0, 0)
        })
        page.addView(banner)

        // Retailer / Administrator Support Card
        val supportCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = cardBg("#111827", "#1E293B", 14)
            setPadding(dp(16), dp(14), dp(16), dp(14))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(14) }
        }
        supportCard.addView(TextView(this).apply {
            text = "ADMINISTRATOR / RETAILER DETAILS"
            textSize = 11f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#60A5FA"))
        })
        val supportName = getString(R.string.support_name)
        val supportPhone = getString(R.string.support_phone)
        supportCard.addView(TextView(this).apply {
            text = "Name   :  $supportName\nContact :  $supportPhone"
            textSize = 14f
            setTextColor(Color.parseColor("#F1F5F9"))
            setPadding(0, dp(6), 0, dp(6))
        })
        supportCard.addView(styledButton("📞 Call Administrator ($supportPhone)", "#2563EB") {
            startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:$supportPhone")))
        })
        page.addView(supportCard)

        // Device Identification Card
        val devCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = cardBg("#111827", "#1E293B", 14)
            setPadding(dp(16), dp(14), dp(16), dp(14))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(12) }
        }
        devCard.addView(TextView(this).apply {
            text = "DEVICE DETAILS"
            textSize = 11f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#60A5FA"))
        })
        devCard.addView(TextView(this).apply {
            textSize = 13f
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(0, dp(6), 0, 0)
            text = """
                Model       : ${Build.MANUFACTURER} ${Build.MODEL} (Android ${Build.VERSION.RELEASE})
                Device ID   : ${state.installationId}
                Connection  : ${state.connection.uppercase()}
                Last Sync   : ${fmt(state.lastSync)}
            """.trimIndent()
        })
        page.addView(devCard)

        // Connectivity & Unlock Sync Controls
        val actionCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = cardBg("#111827", "#1E293B", 14)
            setPadding(dp(16), dp(12), dp(16), dp(14))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(12) }
        }
        actionCard.addView(styledButton("🔄 Check Unlock Status (Sync Now)", "#059669") {
            CommandPollService.syncNow(this@MainActivity)
            Toast.makeText(this@MainActivity, "Checking unlock status with server...", Toast.LENGTH_SHORT).show()
        })
        actionCard.addView(styledButton("📶 Enable Wi-Fi", "#334155") {
            enableWifi()
        })
        actionCard.addView(styledButton("🚨 Emergency Call (112)", "#DC2626") {
            startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:112")))
        })
        page.addView(actionCard)

        setContentView(ScrollView(this).apply {
            setBackgroundColor(Color.parseColor("#070B14"))
            addView(page)
        })
    }

    @Suppress("DEPRECATION")
    private fun enableWifi() {
        try {
            val wm = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            val ok = wm.setWifiEnabled(true)
            if (ok) {
                Toast.makeText(this, "Wi-Fi enabled", Toast.LENGTH_SHORT).show()
            } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startActivity(Intent(Settings.Panel.ACTION_WIFI))
            }
        } catch (_: Exception) {
            Toast.makeText(this, "Wi-Fi toggle requested", Toast.LENGTH_SHORT).show()
        }
    }

    @Deprecated("Back is disabled while restricted")
    override fun onBackPressed() {
        if (!KioskRestrictionManager(this).isApplied()) super.onBackPressed()
    }
}
