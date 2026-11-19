package com.akdevicelock.dpc.lock

import android.content.Context

/**
 * Persists restrictions applied by AK DeviceLock in Device-Protected Storage so the lock state
 * is available during Direct Boot (before the user unlocks their pattern/PIN after a reboot).
 */
class RestrictionState(context: Context) {
    private val dpContext = context.applicationContext.createDeviceProtectedStorageContext()
    private val prefs = dpContext.getSharedPreferences("restriction_state_dp", Context.MODE_PRIVATE)

    var kioskApplied: Boolean
        get() = prefs.getBoolean("kiosk_applied", false)
        set(v) { prefs.edit().putBoolean("kiosk_applied", v).apply() }

    var enrollmentProtected: Boolean
        get() = prefs.getBoolean("enrollment_protected", false)
        set(v) { prefs.edit().putBoolean("enrollment_protected", v).apply() }
}
