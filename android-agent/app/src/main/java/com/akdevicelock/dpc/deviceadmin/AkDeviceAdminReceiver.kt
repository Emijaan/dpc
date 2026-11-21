package com.akdevicelock.dpc.deviceadmin

import android.app.admin.DeviceAdminReceiver
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.PersistableBundle
import android.util.Log
import com.akdevicelock.dpc.R
import com.akdevicelock.dpc.commands.AppState
import com.akdevicelock.dpc.commands.CommandPollService
import com.akdevicelock.dpc.lock.EnrollmentProtection
import com.akdevicelock.dpc.status.MainActivity

class AkDeviceAdminReceiver : DeviceAdminReceiver() {

    override fun onEnabled(context: Context, intent: Intent) {
        Log.i(TAG, "Device admin enabled")
        EnrollmentProtection.enforce(context)
        ensureDefaultsAndStart(context)
    }

    /** Called after QR/NFC/zero-touch provisioning. The QR admin-extras bundle carries the server details. */
    override fun onProfileProvisioningComplete(context: Context, intent: Intent) {
        Log.i(TAG, "Provisioning complete. Device owner=" + isDeviceOwner(context))
        EnrollmentProtection.enforce(context)
        applyAdminExtras(context, intent)
        ensureDefaultsAndStart(context)
        context.startActivity(
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }

    /**
     * Called when Device Owner is transferred from Test DPC (or another DPC) via
     * DevicePolicyManager.transferOwnership().
     */
    override fun onTransferOwnershipComplete(context: Context, bundle: PersistableBundle?) {
        Log.i(TAG, "Ownership transfer complete. Device owner=" + isDeviceOwner(context))
        EnrollmentProtection.enforce(context)
        applyBundle(context, bundle)
        ensureDefaultsAndStart(context)
        context.startActivity(
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }

    companion object {
        private const val TAG = "AkDeviceAdmin"

        fun component(context: Context) =
            ComponentName(context.applicationContext, AkDeviceAdminReceiver::class.java)

        fun isDeviceOwner(context: Context): Boolean {
            val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
            return dpm.isDeviceOwnerApp(context.packageName)
        }

        fun applyAdminExtras(context: Context, intent: Intent?) {
            @Suppress("DEPRECATION")
            val extras = intent?.getParcelableExtra<PersistableBundle>(
                DevicePolicyManager.EXTRA_PROVISIONING_ADMIN_EXTRAS_BUNDLE
            )
            applyBundle(context, extras)
        }

        fun applyBundle(context: Context, extras: PersistableBundle?) {
            if (extras != null) {
                val url = extras.getString("server_url")
                val key = extras.getString("enrollment_key")
                val frp = extras.getString("frp_accounts")
                AppState(context).apply {
                    if (!url.isNullOrBlank() && !key.isNullOrBlank()) {
                        serverUrl = url
                        pendingEnrollmentKey = key
                    }
                    if (!frp.isNullOrBlank()) {
                        frpAccountsCsv = frp
                    }
                }
            }
            ensureDefaultsAndStart(context)
        }

        fun ensureDefaultsAndStart(context: Context) {
            if (!isDeviceOwner(context)) return
            val state = AppState(context)
            if (!state.isRegistered) {
                if (state.serverUrl.isBlank()) {
                    state.serverUrl = context.getString(R.string.default_server_url)
                }
            }
            CommandPollService.start(context)
        }
    }
}
