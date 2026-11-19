package com.akdevicelock.dpc.lock

import android.app.admin.DevicePolicyManager
import android.content.Context
import android.os.UserManager
import com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver

/**
 * Applies and maintains permanent Device Owner protections while the device is enrolled/registered:
 *  - DISALLOW_FACTORY_RESET: blocks factory reset from Android Settings
 *  - DISALLOW_SAFE_BOOT: blocks rebooting into Safe Mode
 *  - DISALLOW_ADD_USER: prevents creating secondary/guest users
 *  - setUninstallBlocked: prevents uninstalling AK DeviceLock
 *
 * These remain active even when the phone is unlocked for normal use, and are only removed
 * upon an authenticated DEVICE_RELEASE command.
 */
object EnrollmentProtection {

    private val ENROLLMENT_RESTRICTIONS = listOf(
        UserManager.DISALLOW_FACTORY_RESET,
        UserManager.DISALLOW_SAFE_BOOT,
        UserManager.DISALLOW_ADD_USER,
    )

    fun enforce(context: Context): Boolean {
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        if (!dpm.isDeviceOwnerApp(context.packageName)) return false
        val admin = AkDeviceAdminReceiver.component(context)
        return try {
            for (r in ENROLLMENT_RESTRICTIONS) {
                dpm.addUserRestriction(admin, r)
            }
            dpm.setUninstallBlocked(admin, context.packageName, true)
            RestrictionState(context).enrollmentProtected = true
            true
        } catch (_: SecurityException) {
            false
        }
    }

    fun isFactoryResetBlocked(context: Context): Boolean {
        val um = context.getSystemService(Context.USER_SERVICE) as UserManager
        return um.hasUserRestriction(UserManager.DISALLOW_FACTORY_RESET)
    }

    /** Called ONLY during authenticated DEVICE_RELEASE before clearing Device Owner. */
    fun releaseAll(context: Context) {
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        if (!dpm.isDeviceOwnerApp(context.packageName)) return
        val admin = AkDeviceAdminReceiver.component(context)
        try {
            for (r in ENROLLMENT_RESTRICTIONS) {
                dpm.clearUserRestriction(admin, r)
            }
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_APPS_CONTROL)
            dpm.setUninstallBlocked(admin, context.packageName, false)
            RestrictionState(context).enrollmentProtected = false
        } catch (_: SecurityException) {}
    }
}

