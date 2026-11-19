package com.akdevicelock.dpc.deviceadmin

import android.app.admin.DeviceAdminReceiver
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.util.Log

class AkDeviceAdminReceiver : DeviceAdminReceiver() {

    override fun onEnabled(context: Context, intent: Intent) {
        Log.i(TAG, "Device admin enabled")
    }

    override fun onProfileProvisioningComplete(context: Context, intent: Intent) {
        Log.i(TAG, "Provisioning complete. Device owner=" + isDeviceOwner(context))
    }

    companion object {
        private const val TAG = "AkDeviceAdmin"

        fun component(context: Context) =
            ComponentName(context.applicationContext, AkDeviceAdminReceiver::class.java)

        fun isDeviceOwner(context: Context): Boolean {
            val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
            return dpm.isDeviceOwnerApp(context.packageName)
        }
    }
}

