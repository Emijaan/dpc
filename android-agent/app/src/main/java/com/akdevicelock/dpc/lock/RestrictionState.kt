package com.akdevicelock.dpc.lock

import android.content.Context

/** Persists only restrictions applied by AK DeviceLock, so unlock reverses only our own changes. */
class RestrictionState(context: Context) {
    private val prefs = context.applicationContext
        .getSharedPreferences("restriction_state", Context.MODE_PRIVATE)

    var kioskApplied: Boolean
        get() = prefs.getBoolean("kiosk_applied", false)
        set(v) { prefs.edit().putBoolean("kiosk_applied", v).apply() }
}

