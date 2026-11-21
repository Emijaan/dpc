package com.akdevicelock.dpc.lock

import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.net.Uri
import android.os.UserManager
import com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver
import com.akdevicelock.dpc.status.MainActivity

/**
 * Bulletproof persistent restriction using Lock Task Mode + Persistent Preferred Home Launcher Alias
 * + Status Bar Disable (official Device Owner APIs):
 *  - Enables LockedHomeAlias and sets it as the Persistent Preferred HOME activity while locked
 *    so there is ZERO home-screen gap on reboot or Home press.
 *  - Disables the status bar / Quick Settings pull-down while locked.
 *  - Whitelists AK DeviceLock and the system dialer (for emergency/support calls).
 *  - Unlock disables LockedHomeAlias, restores the normal Home launcher, re-enables the status bar,
 *    and ends Lock Task Mode while keeping EnrollmentProtection active.
 */
class KioskRestrictionManager(private val context: Context) : LockManager {
    override val name = "KioskRestrictionManager"

    private val dpm =
        context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
    private val admin = AkDeviceAdminReceiver.component(context)
    private val state = RestrictionState(context)
    private val homeAlias = ComponentName(context.packageName, "com.akdevicelock.dpc.status.LockedHomeAlias")

    override fun isSupported() = dpm.isDeviceOwnerApp(context.packageName)

    private fun homeFilter(): IntentFilter = IntentFilter(Intent.ACTION_MAIN).apply {
        addCategory(Intent.CATEGORY_HOME)
        addCategory(Intent.CATEGORY_DEFAULT)
    }

    private fun setHomeAliasEnabled(enabled: Boolean) {
        val flag = if (enabled) PackageManager.COMPONENT_ENABLED_STATE_ENABLED
        else PackageManager.COMPONENT_ENABLED_STATE_DISABLED
        context.packageManager.setComponentEnabledSetting(homeAlias, flag, PackageManager.DONT_KILL_APP)
    }

    override fun lock(): LockResult {
        if (!isSupported()) return LockResult.Failure("Not Device Owner")
        return try {
            EnrollmentProtection.enforce(context)
            dpm.addUserRestriction(admin, UserManager.DISALLOW_APPS_CONTROL)
            dpm.addUserRestriction(admin, UserManager.DISALLOW_UNINSTALL_APPS)
            dpm.addUserRestriction(admin, UserManager.DISALLOW_MODIFY_ACCOUNTS)
            dpm.addUserRestriction(admin, UserManager.DISALLOW_CREATE_WINDOWS)
            dpm.addUserRestriction(admin, UserManager.DISALLOW_CONFIG_DATE_TIME)
            val packages = linkedSetOf(context.packageName)
            dialerPackage()?.let { packages.add(it) }
            dpm.setLockTaskPackages(admin, packages.toTypedArray())
            dpm.setLockTaskFeatures(admin, DevicePolicyManager.LOCK_TASK_FEATURE_NONE)
            setHomeAliasEnabled(true)
            dpm.addPersistentPreferredActivity(admin, homeFilter(), homeAlias)
            try { dpm.setStatusBarDisabled(admin, true) } catch (_: Exception) {}
            state.kioskApplied = true
            context.startActivity(
                Intent(context, MainActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            )
            LockResult.Success
        } catch (e: SecurityException) {
            LockResult.Failure("SecurityException: ${e.message}")
        }
    }

    override fun unlock(): LockResult {
        if (!isSupported()) return LockResult.Failure("Not Device Owner")
        return try {
            state.kioskApplied = false
            dpm.clearPackagePersistentPreferredActivities(admin, context.packageName)
            setHomeAliasEnabled(false)
            try { dpm.setStatusBarDisabled(admin, false) } catch (_: Exception) {}
            dpm.setLockTaskPackages(admin, emptyArray())
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_APPS_CONTROL)
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_UNINSTALL_APPS)
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_MODIFY_ACCOUNTS)
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_CREATE_WINDOWS)
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_CONFIG_DATE_TIME)
            EnrollmentProtection.enforce(context)
            LockResult.Success
        } catch (e: SecurityException) {
            LockResult.Failure("SecurityException: ${e.message}")
        }
    }

    fun isApplied() = state.kioskApplied

    private fun dialerPackage(): String? {
        val i = Intent(Intent.ACTION_DIAL, Uri.parse("tel:112"))
        return context.packageManager.resolveActivity(i, 0)?.activityInfo?.packageName
            ?.takeIf { it != "android" }
    }
}
