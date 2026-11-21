package com.akdevicelock.dpc.commands

import android.content.Context
import android.os.Build
import com.akdevicelock.dpc.BuildConfig
import com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver
import com.akdevicelock.dpc.enrollment.Enrollment
import com.akdevicelock.dpc.lock.EnrollmentProtection
import com.akdevicelock.dpc.lock.KioskRestrictionManager
import com.akdevicelock.dpc.lock.LockResult
import com.akdevicelock.dpc.networking.ApiClient
import com.akdevicelock.dpc.security.CommandVerifier
import com.akdevicelock.dpc.telemetry.TelemetryCollector
import com.akdevicelock.dpc.unlock.RemoteUnlockEngine

/** Validates, de-duplicates, executes and acknowledges commands. Never executes anything unverified. */
class CommandExecutor(private val context: Context, private val api: ApiClient) {
    private val state = AppState(context)
    private val kiosk = KioskRestrictionManager(context)
    private val unlockEngine = RemoteUnlockEngine(context)

    fun handle(c: Command) {
        // Replay / duplicate: never re-execute; just repeat the previous acknowledgment.
        state.processed(c.commandId)?.let {
            api.acknowledge(c.commandId, it.optBoolean("ok"), it.optString("result"))
            return
        }
        if (state.nonceSeen(c.nonce)) {
            finish(c, false, "rejected: nonce_replay"); return
        }
        val reason = CommandVerifier.verify(context, c, state.deviceId, state.nowServerSeconds())
        if (reason != null) {
            finish(c, false, "rejected: $reason"); return
        }
        val (ok, result) = execute(c)
        val acked = finish(c, ok, result)
        if (c.commandType == "DEVICE_RELEASE" && ok && acked) unlockEngine.finalizeRelease()
        else if (c.commandType == "DEVICE_UPDATE" && ok) AppUpdater.installPreparedUpdate(context)
    }

    /** Returns true if the server accepted the acknowledgment. */
    private fun finish(c: Command, ok: Boolean, result: String): Boolean {
        state.recordProcessed(c.commandId, c.nonce, ok, result)
        state.lastCommand = "${c.commandType}: ${if (ok) "OK" else "FAILED"} ($result)"
        return try {
            api.acknowledge(c.commandId, ok, result).code in 200..299
        } catch (e: Exception) {
            false // Recorded locally; the next poll redelivers it and the ack is repeated.
        }
    }

    private fun execute(c: Command): Pair<Boolean, String> = when (c.commandType) {
        "DEVICE_LOCK" -> fromLock(kiosk.lock(), "kiosk restriction applied")
        "DEVICE_UNLOCK" -> unlockEngine.unlock()
        "DEVICE_STATUS" -> true to statusSummary()
        "DEVICE_SYNC" -> true to "synced"
        "DEVICE_LOCATE" -> executeLocate()
        "DEVICE_PHOTO" -> executeCapturePhoto()
        "DEVICE_CAMERA_OFF" -> TelemetryCollector.setCameraDisabled(context, true)
        "DEVICE_CAMERA_ON" -> TelemetryCollector.setCameraDisabled(context, false)
        "DEVICE_GPS_ON" -> executeGpsOn()
        "DEVICE_GPS_UNLOCK" -> TelemetryCollector.setGpsPolicy(context, false)
        "DEVICE_NET_LOCK" -> TelemetryCollector.setNetworkRestricted(context, true)
        "DEVICE_NET_UNLOCK" -> TelemetryCollector.setNetworkRestricted(context, false)
        "DEVICE_UPDATE" -> AppUpdater.prepareUpdate(context, state.serverUrl)
        "DEVICE_RELEASE" -> unlockEngine.prepareRelease()
        else -> false to "unsupported"
    }

    private fun executeLocate(): Pair<Boolean, String> {
        val fix = TelemetryCollector.collectLocation(context, forceFresh = true)
            ?: return false to "location unavailable (GPS off or permission denied)"
        val sync = Enrollment.deviceInfo(context, state)
        TelemetryCollector.appendTelemetry(context, sync, forceFreshGps = false)
        sync.put("latitude", fix.latitude)
        sync.put("longitude", fix.longitude)
        fix.accuracy?.let { sync.put("location_accuracy", it.toDouble()) }
        sync.remove("device_identifier")
        try {
            api.sync(sync)
        } catch (_: Exception) {
        }
        val acc = fix.accuracy?.let { " ±${it.toInt()}m" } ?: ""
        return true to "lat=${"%.5f".format(fix.latitude)},lng=${"%.5f".format(fix.longitude)}$acc"
    }

    private fun executeGpsOn(): Pair<Boolean, String> {
        val res = TelemetryCollector.setGpsPolicy(context, true)
        if (!res.first) return res
        val fix = TelemetryCollector.collectLocation(context, forceFresh = true)
        if (fix != null) {
            val sync = Enrollment.deviceInfo(context, state)
            TelemetryCollector.appendTelemetry(context, sync, forceFreshGps = false)
            sync.put("latitude", fix.latitude)
            sync.put("longitude", fix.longitude)
            fix.accuracy?.let { sync.put("location_accuracy", it.toDouble()) }
            sync.remove("device_identifier")
            try { api.sync(sync) } catch (_: Exception) {}
        }
        return res
    }

    private fun executeCapturePhoto(): Pair<Boolean, String> {
        val (b64, msg) = TelemetryCollector.capturePhotoJpegB64(context)
        if (b64.isNullOrEmpty()) return false to msg
        return try {
            val r = api.uploadPhoto(b64)
            if (r.code in 200..299) true to "photo uploaded (${b64.length} chars)"
            else false to "photo upload error ${r.code}"
        } catch (e: Exception) {
            false to "photo upload failed: ${e.javaClass.simpleName}"
        }
    }

    private fun statusSummary(): String =
        "owner=${AkDeviceAdminReceiver.isDeviceOwner(context)},locked=${kiosk.isApplied()}," +
            "reset_blocked=${EnrollmentProtection.isFactoryResetBlocked(context)}," +
            "sdk=${Build.VERSION.SDK_INT},v=${BuildConfig.VERSION_NAME}"

    private fun fromLock(r: LockResult, okMsg: String): Pair<Boolean, String> = when (r) {
        is LockResult.Success -> true to okMsg
        is LockResult.Failure -> false to r.reason
    }
}
