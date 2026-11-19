package com.akdevicelock.dpc.deviceadmin

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.akdevicelock.dpc.lock.RestrictionState
import com.akdevicelock.dpc.status.MainActivity

/** Re-shows the restriction screen after reboot if a restriction was applied. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED &&
            RestrictionState(context).kioskApplied
        ) {
            context.startActivity(
                Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
        }
    }
}

