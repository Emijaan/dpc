package com.akdevicelock.dpc.unlock

import android.app.admin.DevicePolicyManager
import android.content.Context
import com.akdevicelock.dpc.commands.AppState
import com.akdevicelock.dpc.lock.EnrollmentProtection
import com.akdevicelock.dpc.lock.KioskRestrictionManager
import com.akdevicelock.dpc.lock.LockResult
import com.akdevicelock.dpc.security.SecureStore

/**
 * Reverses only the lock restrictions applied by AK DeviceLock.
 * - unlock(): removes kiosk/lock-task restrictions while keeping EnrollmentProtection
 *   (DISALLOW_FACTORY_RESET, anti-flash, uninstall block) active.
 * - prepareRelease() / finalizeRelease(): removes all restrictions and relinquishes Device Owner.
 */
class RemoteUnlockEngine(private val context: Context) {
    private val kiosk = KioskRestrictionManager(context)

    fun unlock(): Pair<Boolean, String> = when (val r = kiosk.unlock()) {
        is LockResult.Success -> true to "kiosk restriction removed"
        is LockResult.Failure -> false to r.reason
    }

    fun prepareRelease(): Pair<Boolean, String> = when (val r = kiosk.unlock()) {
        is LockResult.Success -> true to "released"
        is LockResult.Failure -> false to r.reason
    }

    /** Called ONLY after the backend has acknowledged DEVICE_RELEASE. */
    fun finalizeRelease() {
        EnrollmentProtection.releaseAll(context)
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        SecureStore(context).clear()
        AppState(context).reset()
        @Suppress("DEPRECATION")
        dpm.clearDeviceOwnerApp(context.packageName)
    }
}

