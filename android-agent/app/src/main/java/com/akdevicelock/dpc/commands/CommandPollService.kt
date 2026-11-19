package com.akdevicelock.dpc.commands

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.os.IBinder
import com.akdevicelock.dpc.enrollment.Enrollment
import com.akdevicelock.dpc.lock.KioskRestrictionManager
import com.akdevicelock.dpc.networking.ApiClient
import com.akdevicelock.dpc.security.SecureStore

/**
 * Polls the authenticated backend for commands. An FCM push (later) would only trigger this same
 * fetch; commands are never trusted from a notification.
 */
class CommandPollService : Service() {
    @Volatile private var running = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("akdl", "AK DeviceLock", NotificationManager.IMPORTANCE_MIN))
        startForeground(1, Notification.Builder(this, "akdl")
            .setContentTitle("AK DeviceLock")
            .setContentText("Device management active")
            .setSmallIcon(android.R.drawable.ic_lock_idle_lock)
            .build())
        if (!running) {
            running = true
            Thread({ loop() }, "akdl-poll").start()
        }
        return START_STICKY
    }

    override fun onDestroy() { running = false }

    private fun online(): Boolean {
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        return cm.activeNetworkInfo?.isConnected == true
    }

    private fun loop() {
        var backoff = POLL_MS
        while (running) {
            val state = AppState(this)
            if (!state.isRegistered && state.pendingEnrollmentKey.isNotEmpty() && state.serverUrl.isNotEmpty()) {
                // QR provisioning delivered the server details; register automatically (retried each cycle).
                if (online()) {
                    val err = Enrollment.register(this, state.serverUrl, state.pendingEnrollmentKey)
                    state.connection = if (err == null) "registered" else "registration pending: $err"
                } else state.connection = "offline (waiting to register)"
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
            try { Thread.sleep(backoff) } catch (_: InterruptedException) {}
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
        private const val POLL_MS = 15_000L
        private const val MAX_BACKOFF_MS = 300_000L

        fun start(context: Context) {
            context.startForegroundService(Intent(context, CommandPollService::class.java))
        }
    }
}

