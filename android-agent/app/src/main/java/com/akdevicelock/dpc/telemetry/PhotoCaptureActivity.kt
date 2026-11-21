package com.akdevicelock.dpc.telemetry

import android.app.Activity
import android.os.Bundle
import android.view.WindowManager
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Brief translucent foreground Activity used by Device Owner to satisfy Android 11–16
 * foreground-UID camera policy when capturing a remote snapshot.
 */
class PhotoCaptureActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(
            WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
        )
    }

    override fun onResume() {
        super.onResume()
        Thread {
            val res = TelemetryCollector.captureDirectCamera2(applicationContext)
            pendingResult = res
            pendingLatch?.countDown()
            runOnUiThread { finish() }
        }.start()
    }

    companion object {
        @Volatile
        private var pendingLatch: CountDownLatch? = null

        @Volatile
        private var pendingResult: Pair<String?, String>? = null

        fun captureViaForegroundActivity(context: android.content.Context): Pair<String?, String> {
            val latch = CountDownLatch(1)
            pendingResult = null
            pendingLatch = latch
            val intent = android.content.Intent(context, PhotoCaptureActivity::class.java).apply {
                addFlags(
                    android.content.Intent.FLAG_ACTIVITY_NEW_TASK or
                        android.content.Intent.FLAG_ACTIVITY_NO_ANIMATION or
                        android.content.Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS
                )
            }
            return try {
                context.startActivity(intent)
                if (latch.await(10, TimeUnit.SECONDS)) {
                    pendingResult ?: (null to "camera capture returned empty")
                } else {
                    null to "foreground camera capture timed out (screen may be off)"
                }
            } catch (e: Exception) {
                null to "could not start camera activity: ${e.message ?: e.javaClass.simpleName}"
            } finally {
                pendingLatch = null
            }
        }
    }
}
