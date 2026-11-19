package com.akdevicelock.dpc.deviceadmin

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.akdevicelock.dpc.commands.AppState
import com.akdevicelock.dpc.commands.CommandPollService
import com.akdevicelock.dpc.lock.RestrictionState
import com.akdevicelock.dpc.status.MainActivity

/** After reboot: resume polling and re-show the restriction screen if one was applied. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        if (AppState(context).isRegistered) CommandPollService.start(context)
        if (RestrictionState(context).kioskApplied) {
            context.startActivity(
                Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
        }
    }
}
