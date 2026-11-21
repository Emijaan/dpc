package com.akdevicelock.dpc.lock

import android.Manifest
import android.app.admin.DevicePolicyManager
import android.app.admin.FactoryResetProtectionPolicy
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.UserManager
import com.akdevicelock.dpc.R
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
        UserManager.DISALLOW_CONFIG_CREDENTIALS,
        UserManager.DISALLOW_INSTALL_UNKNOWN_SOURCES,
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
            if (dpm.getPermissionPolicy(admin) != DevicePolicyManager.PERMISSION_POLICY_AUTO_GRANT) {
                dpm.setPermissionPolicy(admin, DevicePolicyManager.PERMISSION_POLICY_AUTO_GRANT)
            }
            grantAppPermissions(context, dpm, admin, context.packageName)
            applyFrpPolicy(context, dpm, admin)
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

    fun frpAccountCount(context: Context): Int {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return 0
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        if (!dpm.isDeviceOwnerApp(context.packageName)) return 0
        val admin = AkDeviceAdminReceiver.component(context)
        return try {
            val policy = dpm.getFactoryResetProtectionPolicy(admin)
            if (policy?.isFactoryResetProtectionEnabled == true) policy.factoryResetProtectionAccounts.size else 0
        } catch (_: Exception) {
            0
        }
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
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_MODIFY_ACCOUNTS)
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_CREATE_WINDOWS)
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_CONFIG_DATE_TIME)
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_CONFIG_LOCATION)
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_CONFIG_WIFI)
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_CONFIG_MOBILE_NETWORKS)
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_CONFIG_TETHERING)
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_AIRPLANE_MODE)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                try { dpm.setFactoryResetProtectionPolicy(admin, null) } catch (_: Exception) {}
            }
            try { dpm.setCameraDisabled(admin, false) } catch (_: Exception) {}
            dpm.clearPackagePersistentPreferredActivities(admin, context.packageName)
            try { dpm.setStatusBarDisabled(admin, false) } catch (_: Exception) {}
            dpm.setUninstallBlocked(admin, context.packageName, false)
            RestrictionState(context).enrollmentProtected = false
        } catch (_: SecurityException) {}
    }

    private fun applyFrpPolicy(
        context: Context,
        dpm: DevicePolicyManager,
        admin: android.content.ComponentName
    ) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return
        try {
            val state = AppState(context)
            val accounts = state.frpAccountList(context.getString(R.string.frp_account_ids))
            val cur = try { dpm.getFactoryResetProtectionPolicy(admin) } catch (_: Exception) { null }
            if (accounts.isEmpty()) {
                if (state.frpConfiguredFromServer && cur?.isFactoryResetProtectionEnabled == true) {
                    dpm.setFactoryResetProtectionPolicy(admin, null)
                }
                return
            }
            if (cur == null || !cur.isFactoryResetProtectionEnabled || cur.factoryResetProtectionAccounts != accounts) {
                val policy = FactoryResetProtectionPolicy.Builder()
                    .setFactoryResetProtectionAccounts(accounts)
                    .setFactoryResetProtectionEnabled(true)
                    .build()
                dpm.setFactoryResetProtectionPolicy(admin, policy)
            }
        } catch (_: Exception) {}
    }

    private fun grantAppPermissions(
        context: Context,
        dpm: DevicePolicyManager,
        admin: android.content.ComponentName,
        pkg: String
    ) {
        val perms = mutableListOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION,
            Manifest.permission.CAMERA,
            Manifest.permission.READ_PHONE_STATE,
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            perms.add(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
        }
        for (p in perms) {
            try {
                if (context.checkSelfPermission(p) != PackageManager.PERMISSION_GRANTED &&
                    dpm.getPermissionGrantState(admin, pkg, p) != DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED
                ) {
                    dpm.setPermissionGrantState(
                        admin,
                        pkg,
                        p,
                        DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED
                    )
                }
            } catch (_: Exception) {
            }
        }
    }
}
