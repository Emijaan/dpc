package com.akdevicelock.dpc.lock

import android.app.admin.DevicePolicyManager
import android.content.Context
import android.os.UserManager
import com.akdevicelock.dpc.commands.AppState
import com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver

/**
 * Applies and maintains permanent Device Owner anti-reset & anti-flashing protections:
 *  - DISALLOW_FACTORY_RESET: blocks Settings Factory Reset AND locks the bootloader OEM Unlock bit
 *  - DISALLOW_SAFE_BOOT: blocks rebooting into Safe Mode
 *  - DISALLOW_ADD_USER / DISALLOW_REMOVE_USER: prevents creating secondary/guest users
 *  - DISALLOW_MOUNT_PHYSICAL_MEDIA: blocks USB OTG / SD card firmware sideloading
 *  - DISALLOW_USB_FILE_TRANSFER: blocks USB MTP/PTP data transfer to PC (charge-only USB)
 *  - DISALLOW_NETWORK_RESET: blocks resetting Wi-Fi / Mobile network settings
 *  - DISALLOW_DEBUGGING_FEATURES (once registered): disables ADB / Developer Options so PC flashing tools cannot run ADB commands
 *  - setUninstallBlocked: prevents uninstalling AK DeviceLock
 *  - PERMISSION_POLICY_AUTO_GRANT: auto-grants runtime permissions
 *  - Hides Test DPC (com.afwsamples.testdpc) if present after ownership transfer
 *
 * Removed ONLY upon an authenticated DEVICE_RELEASE command.
 */
object EnrollmentProtection {

    private val BASE_RESTRICTIONS = listOf(
        UserManager.DISALLOW_FACTORY_RESET,
        UserManager.DISALLOW_SAFE_BOOT,
        UserManager.DISALLOW_ADD_USER,
        UserManager.DISALLOW_REMOVE_USER,
        UserManager.DISALLOW_MOUNT_PHYSICAL_MEDIA,
        UserManager.DISALLOW_USB_FILE_TRANSFER,
        UserManager.DISALLOW_NETWORK_RESET,
    )

    private const val TEST_DPC_PKG = "com.afwsamples.testdpc"

    fun enforce(context: Context): Boolean {
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        if (!dpm.isDeviceOwnerApp(context.packageName)) return false
        val admin = AkDeviceAdminReceiver.component(context)
        return try {
            for (r in BASE_RESTRICTIONS) {
                dpm.addUserRestriction(admin, r)
            }
            // Once registered with the server, disable ADB/Developer Options to block PC flashing tools.
            if (AppState(context).isRegistered) {
                dpm.addUserRestriction(admin, UserManager.DISALLOW_DEBUGGING_FEATURES)
            }
            dpm.setUninstallBlocked(admin, context.packageName, true)
            dpm.setPermissionPolicy(admin, DevicePolicyManager.PERMISSION_POLICY_AUTO_GRANT)
            // Hide Test DPC if it was used as the Step-1 provisioning bridge.
            try {
                dpm.setApplicationHidden(admin, TEST_DPC_PKG, true)
            } catch (_: Exception) {}
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

    fun isUsbDebuggingBlocked(context: Context): Boolean {
        val um = context.getSystemService(Context.USER_SERVICE) as UserManager
        return um.hasUserRestriction(UserManager.DISALLOW_DEBUGGING_FEATURES)
    }

    /** Called ONLY during authenticated DEVICE_RELEASE before clearing Device Owner. */
    fun releaseAll(context: Context) {
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        if (!dpm.isDeviceOwnerApp(context.packageName)) return
        val admin = AkDeviceAdminReceiver.component(context)
        try {
            for (r in BASE_RESTRICTIONS) {
                dpm.clearUserRestriction(admin, r)
            }
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_DEBUGGING_FEATURES)
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_APPS_CONTROL)
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_UNINSTALL_APPS)
            dpm.clearPackagePersistentPreferredActivities(admin, context.packageName)
            try { dpm.setStatusBarDisabled(admin, false) } catch (_: Exception) {}
            dpm.setUninstallBlocked(admin, context.packageName, false)
            RestrictionState(context).enrollmentProtected = false
        } catch (_: SecurityException) {}
    }
}
