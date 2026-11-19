package com.akdevicelock.dpc.commands

import android.content.Context
import android.os.Build
import com.akdevicelock.dpc.BuildConfig
import com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver
import com.akdevicelock.dpc.lock.EnrollmentProtection
import com.akdevicelock.dpc.lock.KioskRestrictionManager
import com.akdevicelock.dpc.lock.LockResult
import com.akdevicelock.dpc.networking.ApiClient
import com.akdevicelock.dpc.security.CommandVerifier
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
        "DEVICE_RELEASE" -> unlockEngine.prepareRelease()
        else -> false to "unsupported"
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
