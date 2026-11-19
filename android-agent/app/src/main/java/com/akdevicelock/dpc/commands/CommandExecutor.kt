package com.akdevicelock.dpc.commands

import android.app.admin.DevicePolicyManager
import android.content.Context
import com.akdevicelock.dpc.lock.EnrollmentProtection
import com.akdevicelock.dpc.lock.KioskRestrictionManager
import com.akdevicelock.dpc.lock.LockResult
import com.akdevicelock.dpc.networking.ApiClient
import com.akdevicelock.dpc.security.CommandVerifier
import com.akdevicelock.dpc.security.SecureStore

/** Validates, de-duplicates, executes and acknowledges commands. Never executes anything unverified. */
class CommandExecutor(private val context: Context, private val api: ApiClient) {
    private val state = AppState(context)
    private val kiosk = KioskRestrictionManager(context)

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
        if (c.commandType == "DEVICE_RELEASE" && ok && acked) finalizeRelease()
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
        "DEVICE_UNLOCK" -> fromLock(kiosk.unlock(), "kiosk restriction removed")
        "DEVICE_STATUS", "DEVICE_SYNC" -> true to "synced"
        "DEVICE_RELEASE" -> fromLock(kiosk.unlock(), "released")
        else -> false to "unsupported"
    }

    private fun fromLock(r: LockResult, okMsg: String): Pair<Boolean, String> = when (r) {
        is LockResult.Success -> true to okMsg
        is LockResult.Failure -> false to r.reason
    }

    /** Authorized release, after the server acknowledged: clear protections, forget credentials, give up Device Owner. */
    private fun finalizeRelease() {
        EnrollmentProtection.releaseAll(context)
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        SecureStore(context).clear()
        state.reset()
        @Suppress("DEPRECATION")
        dpm.clearDeviceOwnerApp(context.packageName)
    }
}
