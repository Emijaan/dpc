package com.akdevicelock.dpc.deviceadmin

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.akdevicelock.dpc.commands.AppState
import com.akdevicelock.dpc.commands.CommandPollService
import com.akdevicelock.dpc.lock.EnrollmentProtection
import com.akdevicelock.dpc.lock.KioskRestrictionManager
import com.akdevicelock.dpc.lock.RestrictionState
import com.akdevicelock.dpc.status.MainActivity

/**
 * Direct-Boot aware receiver: runs on both ACTION_LOCKED_BOOT_COMPLETED (before user enters PIN/pattern)
 * and ACTION_BOOT_COMPLETED, immediately re-enforcing protections and launching the lock screen with zero gap.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return
        if (action != Intent.ACTION_BOOT_COMPLETED && action != Intent.ACTION_LOCKED_BOOT_COMPLETED) return
        EnrollmentProtection.enforce(context)
        if (RestrictionState(context).kioskApplied) {
            KioskRestrictionManager(context).lock()
            context.startActivity(
                Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
        }
        if (action == Intent.ACTION_BOOT_COMPLETED && AppState(context).isRegistered) {
            CommandPollService.start(context)
        }
    }
}
