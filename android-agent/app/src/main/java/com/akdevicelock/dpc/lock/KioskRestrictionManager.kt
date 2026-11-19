package com.akdevicelock.dpc.lock

import android.app.admin.DevicePolicyManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.UserManager
import com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver
import com.akdevicelock.dpc.status.MainActivity

/**
 * Persistent restriction using Lock Task Mode (official Device Owner API).
 * The app whitelists itself and the system dialer (for emergency calls) and disables
 * all other lock-task features (no home, recents, notifications, status bar actions).
 * Unlock removes the whitelist, which ends lock task mode, while keeping enrollment
 * protections (DISALLOW_FACTORY_RESET, DISALLOW_SAFE_BOOT, uninstall block) active.
 */
class KioskRestrictionManager(private val context: Context) : LockManager {
    override val name = "KioskRestrictionManager"

    private val dpm =
        context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
    private val admin = AkDeviceAdminReceiver.component(context)
    private val state = RestrictionState(context)

    override fun isSupported() = dpm.isDeviceOwnerApp(context.packageName)

    override fun lock(): LockResult {
        if (!isSupported()) return LockResult.Failure("Not Device Owner")
        return try {
            EnrollmentProtection.enforce(context)
            dpm.addUserRestriction(admin, UserManager.DISALLOW_APPS_CONTROL)
            val packages = linkedSetOf(context.packageName)
            dialerPackage()?.let { packages.add(it) }
            dpm.setLockTaskPackages(admin, packages.toTypedArray())
            dpm.setLockTaskFeatures(admin, DevicePolicyManager.LOCK_TASK_FEATURE_NONE)
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
            dpm.setLockTaskPackages(admin, emptyArray())
            dpm.clearUserRestriction(admin, UserManager.DISALLOW_APPS_CONTROL)
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
