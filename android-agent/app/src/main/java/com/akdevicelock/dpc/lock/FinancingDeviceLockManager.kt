package com.akdevicelock.dpc.lock

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build

/**
 * Wrapper for Android 14+ (API 34+) android.app.devicelock.DeviceLockManager.
 *
 * DeviceLockManager is restricted to apps holding the system FINANCING role
 * (android.app.role.FINANCING) and MANAGE_DEVICE_LOCK_STATE permission, which are only
 * granted on compatible OEM-enabled financing builds (e.g. via Google Play / OEM kiosk role).
 * Standard Device Owner apps on consumer devices do NOT hold this role, so isSupported()
 * returns false honestly rather than faking lock behavior.
 */
class FinancingDeviceLockManager(private val context: Context) : LockManager {
    override val name = "FinancingDeviceLockManager"

    private fun serviceOrNull(): Any? {
        if (Build.VERSION.SDK_INT < 34) return null
        return try {
            context.getSystemService("device_lock")
        } catch (_: Throwable) {
            null
        }
    }

    override fun isSupported(): Boolean {
        if (Build.VERSION.SDK_INT < 34) return false
        if (serviceOrNull() == null) return false
        return context.checkSelfPermission("android.permission.MANAGE_DEVICE_LOCK_STATE") ==
            PackageManager.PERMISSION_GRANTED
    }

    override fun lock(): LockResult {
        if (Build.VERSION.SDK_INT < 34) {
            return LockResult.Failure("DeviceLockManager requires Android 14+ (API 34+)")
        }
        val svc = serviceOrNull() ?: return LockResult.Failure("DeviceLockManager service unavailable")
        if (!isSupported()) {
            return LockResult.Failure("Device does not hold FINANCING role / MANAGE_DEVICE_LOCK_STATE")
        }
        return try {
            val m = svc.javaClass.getMethod("lockDevice", java.util.concurrent.Executor::class.java, Class.forName("android.os.OutcomeReceiver"))
            // OutcomeReceiver invocation requires API 34+ financing role; verified above.
            @Suppress("UNUSED_VARIABLE") val _ref = m
            LockResult.Failure("Financing role callback integration pending OEM financing device")
        } catch (e: Throwable) {
            LockResult.Failure("DeviceLockManager error: ${e.message}")
        }
    }

    override fun unlock(): LockResult {
        if (!isSupported()) {
            return LockResult.Failure("DeviceLockManager not supported on this device/role")
        }
        return LockResult.Failure("Financing role callback integration pending OEM financing device")
    }
}

