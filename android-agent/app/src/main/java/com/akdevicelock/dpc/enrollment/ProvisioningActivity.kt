package com.akdevicelock.dpc.enrollment

import android.app.Activity
import android.app.admin.DevicePolicyManager
import android.content.Intent
import android.os.Bundle
import com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver

/**
 * Required by Android 10+ provisioning (GET_PROVISIONING_MODE / ADMIN_POLICY_COMPLIANCE).
 * Accepts fully-managed-device mode and applies admin extras bundle if provided.
 */
class ProvisioningActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        AkDeviceAdminReceiver.applyAdminExtras(this, intent)
        val result = Intent()
        if (intent?.action == DevicePolicyManager.ACTION_GET_PROVISIONING_MODE) {
            result.putExtra(
                DevicePolicyManager.EXTRA_PROVISIONING_MODE,
                DevicePolicyManager.PROVISIONING_MODE_FULLY_MANAGED_DEVICE
            )
        }
        setResult(RESULT_OK, result)
        finish()
    }
}
