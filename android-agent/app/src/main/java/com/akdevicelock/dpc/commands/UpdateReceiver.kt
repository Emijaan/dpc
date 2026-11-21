package com.akdevicelock.dpc.commands

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller

/** Captures PackageInstaller session results for silent DEVICE_UPDATE self-installs. */
class UpdateReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
        val msg = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE).orEmpty()
        AppUpdater.stagedFile(context).delete()
        if (status != PackageInstaller.STATUS_SUCCESS) {
            AppState(context).lastCommand = "DEVICE_UPDATE install status=$status $msg".trim()
        }
    }
}
