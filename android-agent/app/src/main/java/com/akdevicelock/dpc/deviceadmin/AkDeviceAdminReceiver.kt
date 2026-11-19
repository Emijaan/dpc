package com.akdevicelock.dpc.deviceadmin

import android.app.admin.DeviceAdminReceiver
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.PersistableBundle
import android.util.Log
import com.akdevicelock.dpc.commands.AppState
import com.akdevicelock.dpc.commands.CommandPollService
import com.akdevicelock.dpc.lock.EnrollmentProtection
import com.akdevicelock.dpc.status.MainActivity

class AkDeviceAdminReceiver : DeviceAdminReceiver() {

    override fun onEnabled(context: Context, intent: Intent) {
        Log.i(TAG, "Device admin enabled")
        EnrollmentProtection.enforce(context)
    }

    /** Called after QR/NFC/zero-touch provisioning. The QR admin-extras bundle carries the server details. */
    override fun onProfileProvisioningComplete(context: Context, intent: Intent) {
        Log.i(TAG, "Provisioning complete. Device owner=" + isDeviceOwner(context))
        EnrollmentProtection.enforce(context)
        applyAdminExtras(context, intent)
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
            ) ?: return
            val url = extras.getString("server_url")
            val key = extras.getString("enrollment_key")
            if (!url.isNullOrBlank() && !key.isNullOrBlank()) {
                AppState(context).apply {
                    serverUrl = url
                    pendingEnrollmentKey = key
                }
                CommandPollService.start(context)
            }
        }
    }
}
