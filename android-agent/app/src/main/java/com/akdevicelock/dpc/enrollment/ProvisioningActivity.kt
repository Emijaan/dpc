package com.akdevicelock.dpc.enrollment

import android.app.Activity
import android.app.admin.DevicePolicyManager
import android.content.Intent
import android.os.Bundle
import com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver
import com.akdevicelock.dpc.lock.EnrollmentProtection
import com.akdevicelock.dpc.status.MainActivity

/**
 * Handles Android 10–16+ provisioning actions:
 *  - ACTION_GET_PROVISIONING_MODE: selects PROVISIONING_MODE_FULLY_MANAGED_DEVICE (Device Owner)
 *  - ACTION_ADMIN_POLICY_COMPLIANCE: enforces protections, saves QR extras, starts poll service
 *  - ACTION_PROVISIONING_SUCCESSFUL: opens MainActivity
 */
class ProvisioningActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val result = Intent()
        try {
            when (intent?.action) {
                DevicePolicyManager.ACTION_GET_PROVISIONING_MODE -> {
                    result.putExtra(
                        DevicePolicyManager.EXTRA_PROVISIONING_MODE,
                        DevicePolicyManager.PROVISIONING_MODE_FULLY_MANAGED_DEVICE
                    )
                }
                DevicePolicyManager.ACTION_ADMIN_POLICY_COMPLIANCE -> {
                    EnrollmentProtection.enforce(this)
                    AkDeviceAdminReceiver.applyAdminExtras(this, intent)
                }
                "android.app.action.PROVISIONING_SUCCESSFUL" -> {
                    EnrollmentProtection.enforce(this)
                    AkDeviceAdminReceiver.ensureDefaultsAndStart(this)
                    startActivity(Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                }
                else -> {
                    AkDeviceAdminReceiver.applyAdminExtras(this, intent)
                }
            }
        } catch (_: Exception) {}
        setResult(RESULT_OK, result)
        finish()
    }
}
