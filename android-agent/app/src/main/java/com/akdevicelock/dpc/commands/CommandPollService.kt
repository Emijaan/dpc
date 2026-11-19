package com.akdevicelock.dpc.commands

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.os.IBinder
import com.akdevicelock.dpc.R
import com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver
import com.akdevicelock.dpc.enrollment.Enrollment
import com.akdevicelock.dpc.lock.EnrollmentProtection
import com.akdevicelock.dpc.lock.KioskRestrictionManager
import com.akdevicelock.dpc.networking.ApiClient
import com.akdevicelock.dpc.security.SecureStore

/**
 * Polls the authenticated backend for commands every 4 seconds (and on instant sync triggers).
 * Auto-registers when the device becomes Device Owner (via QR or Test DPC ownership transfer).
 */
class CommandPollService : Service() {
    @Volatile private var running = false
    @Volatile private var pollThread: Thread? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("akdl", "AK DeviceLock", NotificationManager.IMPORTANCE_MIN))
        startForeground(1, Notification.Builder(this, "akdl")
            .setContentTitle("AK DeviceLock")
            .setContentText("Enterprise device protection active")
            .setSmallIcon(android.R.drawable.ic_lock_idle_lock)
            .build())
        if (!running) {
            running = true
            pollThread = Thread({ loop() }, "akdl-poll").also { it.start() }
        } else if (intent?.getBooleanExtra(EXTRA_FORCE_SYNC, false) == true) {
            pollThread?.interrupt()
        }
        return START_STICKY
    }

    override fun onDestroy() { running = false }

    @Suppress("DEPRECATION")
    private fun online(): Boolean {
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        return cm.activeNetworkInfo?.isConnected == true
    }

    private fun loop() {
        var backoff = POLL_MS
        while (running) {
            EnrollmentProtection.enforce(this)
            val state = AppState(this)
            if (!state.isRegistered && AkDeviceAdminReceiver.isDeviceOwner(this)) {
                val url = state.serverUrl.ifBlank { getString(R.string.default_server_url) }
                val key = state.pendingEnrollmentKey.ifBlank { getString(R.string.default_enrollment_key) }
                if (url.isNotEmpty() && key.isNotEmpty()) {
                    if (online()) {
                        val err = Enrollment.register(this, url, key)
                        state.connection = if (err == null) "online" else "registration pending: $err"
                    } else {
                        state.connection = "offline (waiting to register)"
                    }
                }
            }
            if (state.isRegistered) {
                if (!online()) {
                    state.connection = "offline (no network)"
                    backoff = POLL_MS
                } else {
                    backoff = try { cycle(state); POLL_MS } catch (e: Exception) {
                        state.connection = "server unreachable"
                        minOf(backoff * 2, MAX_BACKOFF_MS)
                    }
                }
            }
            try { Thread.sleep(backoff) } catch (_: InterruptedException) { backoff = POLL_MS }
        }
    }

    private fun cycle(state: AppState) {
        val token = SecureStore(this).getToken() ?: run { state.connection = "no credential"; return }
        val api = ApiClient(state.serverUrl, token)
        val pending = api.pending()
        if (pending.code == 401) { state.connection = "credential rejected"; return }
        val body = pending.body ?: throw IllegalStateException("bad response")
        state.serverOffset = body.getLong("server_time") - System.currentTimeMillis() / 1000
        val cmds = body.getJSONArray("commands")
        val executor = CommandExecutor(this, api)
        for (i in 0 until cmds.length()) {
            Command.parse(cmds.getJSONObject(i))?.let { executor.handle(it) }
            if (!state.isRegistered) return // released
        }
        val sync = Enrollment.deviceInfo(this, state)
            .put("restriction_status", if (KioskRestrictionManager(this).isApplied()) "LOCKED" else "NONE")
        sync.remove("device_identifier")
        api.sync(sync)
        state.lastSync = System.currentTimeMillis()
        state.connection = "online"
    }

    companion object {
        private const val POLL_MS = 4_000L
        private const val MAX_BACKOFF_MS = 30_000L
        private const val EXTRA_FORCE_SYNC = "force_sync"

        fun start(context: Context) {
            context.startForegroundService(Intent(context, CommandPollService::class.java))
        }

        fun syncNow(context: Context) {
            context.startForegroundService(
                Intent(context, CommandPollService::class.java).putExtra(EXTRA_FORCE_SYNC, true)
            )
        }
    }
}
