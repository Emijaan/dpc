package com.akdevicelock.dpc.lock

import android.app.admin.DevicePolicyManager
import android.content.Context
import com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver

/**
 * Uses DevicePolicyManager.lockNow(): locks the screen once. The user can unlock with
 * their own PIN/pattern/biometrics. It is NOT persistent and cannot be "unlocked" remotely;
 * unlock() therefore has nothing to reverse and reports that honestly.
 */
class DevicePolicyLockManager(private val context: Context) : LockManager {
    override val name = "DevicePolicyLockManager"

    private val dpm =
        context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager

    override fun isSupported() = dpm.isAdminActive(AkDeviceAdminReceiver.component(context))

    override fun lock(): LockResult {
        if (!isSupported()) return LockResult.Failure("Device admin not active")
        return try {
            dpm.lockNow()
            LockResult.Success
        } catch (e: SecurityException) {
            LockResult.Failure("SecurityException: ${e.message}")
        }
    }

    override fun unlock(): LockResult =
        LockResult.Failure("lockNow() has no remote unlock; nothing applied to reverse")
}

