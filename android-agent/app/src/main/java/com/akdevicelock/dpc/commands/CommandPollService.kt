package com.akdevicelock.dpc.commands

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.os.Build
import android.os.IBinder
import com.akdevicelock.dpc.R
import com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver
import com.akdevicelock.dpc.enrollment.Enrollment
import com.akdevicelock.dpc.lock.EnrollmentProtection
import com.akdevicelock.dpc.lock.KioskRestrictionManager
import com.akdevicelock.dpc.networking.ApiClient
import com.akdevicelock.dpc.security.CommandVerifier
import com.akdevicelock.dpc.security.DeviceKeyManager
import com.akdevicelock.dpc.security.SecureStore
import com.akdevicelock.dpc.telemetry.TelemetryCollector

/**
 * Polls the authenticated backend for commands every 4 seconds (and immediately on network
 * restoration or sync triggers). Periodically renews the device-specific credential.
 */
class CommandPollService : Service() {
    @Volatile private var running = false
    @Volatile private var pollThread: Thread? = null
    private var lastLocationSyncMs = 0L
    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        registerConnectivityWatcher()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("akdl", "AK DeviceLock", NotificationManager.IMPORTANCE_MIN))
        val notif = Notification.Builder(this, "akdl")
            .setContentTitle("AK DeviceLock")
            .setContentText("Enterprise device protection active")
            .setSmallIcon(android.R.drawable.ic_lock_idle_lock)
            .build()
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(1, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(1, notif)
        }
        if (!running) {
            running = true
            pollThread = Thread({ loop() }, "akdl-poll").also { it.start() }
        } else if (intent?.getBooleanExtra(EXTRA_FORCE_SYNC, false) == true) {
            pollThread?.interrupt()
        }
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        networkCallback?.let {
            try {
                (getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager).unregisterNetworkCallback(it)
            } catch (_: Exception) {}
        }
    }

    private fun registerConnectivityWatcher() {
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val cb = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                pollThread?.interrupt()
            }
        }
        try {
            cm.registerDefaultNetworkCallback(cb)
            networkCallback = cb
        } catch (_: Exception) {}
    }

    private fun online(): Boolean {
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val net = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(net) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    private fun loop() {
        var backoff = POLL_MS
        while (running) {
            EnrollmentProtection.enforce(this)
            val state = AppState(this)
            if (!state.isRegistered && AkDeviceAdminReceiver.isDeviceOwner(this)) {
                val url = state.serverUrl.ifBlank { getString(R.string.default_server_url) }
                val key = state.pendingEnrollmentKey
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
        val store = SecureStore(this)
        val token = store.getToken() ?: run { state.connection = "no credential"; return }
        var api = ApiClient(state.serverUrl, token)
        syncKeyBundle(state, api)
        if (!state.deviceKeyRegistered && state.deviceId.isNotEmpty()) {
            DeviceKeyManager.getOrCreatePublicKeyB64()?.let { pub ->
                val kr = api.registerDevicePublicKey(state.deviceId, pub)
                if (kr.code in 200..299) state.deviceKeyRegistered = true
            }
        }
        val pending = api.pending()
        if (pending.code == 401) { state.connection = "credential rejected"; return }
        val body = pending.body ?: throw IllegalStateException("bad response")
        state.serverOffset = body.getLong("server_time") - System.currentTimeMillis() / 1000
        state.updateLockScreenInfo(body.optJSONObject("lock_screen"))
        val cmds = body.getJSONArray("commands")
        val executor = CommandExecutor(this, api)
        for (i in 0 until cmds.length()) {
            Command.parse(cmds.getJSONObject(i))?.let { executor.handle(it) }
            if (!state.isRegistered) return // released
        }
        val now = System.currentTimeMillis()
        if (state.lastTokenRenewal == 0L) {
            state.lastTokenRenewal = now
        } else if (now - state.lastTokenRenewal > TOKEN_RENEW_MS) {
            val renewed = api.renewToken()
            val newTok = renewed.body?.optString("device_token", "").orEmpty()
            if (renewed.code in 200..299 && newTok.isNotEmpty()) {
                store.putToken(newTok)
                state.lastTokenRenewal = now
                api = ApiClient(state.serverUrl, newTok)
            }
        }
        val includeLoc = now - lastLocationSyncMs >= LOCATION_SYNC_MS
        val sync = Enrollment.deviceInfo(this, state)
            .put("restriction_status", if (KioskRestrictionManager(this).isApplied()) "LOCKED" else "NONE")
        TelemetryCollector.appendTelemetry(this, sync, forceFreshGps = false, includeLocation = includeLoc)
        if (includeLoc) lastLocationSyncMs = now
        sync.remove("device_identifier")
        val syncRes = api.sync(sync)
        syncRes.body?.optJSONObject("lock_screen")?.let { state.updateLockScreenInfo(it) }
        state.lastSync = now
        state.connection = "online"
    }

    private fun syncKeyBundle(state: AppState, api: ApiClient) {
        try {
            val kr = api.fetchPublicKeys()
            val body = kr.body ?: return
            if (kr.code !in 200..299) return
            val valid = mutableMapOf<String, String>()
            val arr = body.optJSONArray("valid_keys")
            if (arr != null) {
                for (i in 0 until arr.length()) {
                    val o = arr.getJSONObject(i)
                    valid[o.getString("key_id")] = o.getString("public_key_b64")
                }
            }
            val revoked = mutableSetOf<String>()
            val rarr = body.optJSONArray("revoked_key_ids")
            if (rarr != null) {
                for (i in 0 until rarr.length()) revoked.add(rarr.getString(i))
            }
            state.updateKeyBundle(valid, revoked)
        } catch (_: Exception) {}
    }

    companion object {
        private const val POLL_MS = 4_000L
        private const val LOCATION_SYNC_MS = 300_000L
        private const val MAX_BACKOFF_MS = 30_000L
        private const val TOKEN_RENEW_MS = 7L * 24 * 3600 * 1000L
        private const val EXTRA_FORCE_SYNC = "force_sync"

        fun start(context: Context) {
            try {
                context.startForegroundService(Intent(context, CommandPollService::class.java))
            } catch (_: Exception) {}
        }

        fun syncNow(context: Context) {
            try {
                context.startForegroundService(
                    Intent(context, CommandPollService::class.java).putExtra(EXTRA_FORCE_SYNC, true)
                )
            } catch (_: Exception) {}
        }
    }
}
