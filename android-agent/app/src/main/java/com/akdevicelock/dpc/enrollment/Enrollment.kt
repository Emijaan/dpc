package com.akdevicelock.dpc.enrollment

import android.content.Context
import android.os.Build
import com.akdevicelock.dpc.BuildConfig
import com.akdevicelock.dpc.commands.AppState
import com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver
import com.akdevicelock.dpc.networking.ApiClient
import com.akdevicelock.dpc.security.SecureStore
import org.json.JSONObject

object Enrollment {

    fun deviceInfo(context: Context, state: AppState): JSONObject = JSONObject()
        .put("device_identifier", state.installationId)
        .put("manufacturer", Build.MANUFACTURER.take(64))
        .put("model", Build.MODEL.take(64))
        .put("android_version", Build.VERSION.RELEASE.take(16))
        .put("sdk_version", Build.VERSION.SDK_INT)
        .put("app_version", BuildConfig.VERSION_NAME)

    /** Blocking. Returns null on success, otherwise an error message. Call off the main thread. */
    fun register(context: Context, serverUrl: String, enrollmentKey: String): String? {
        if (!AkDeviceAdminReceiver.isDeviceOwner(context)) return "App is not Device Owner"
        val state = AppState(context)
        state.serverUrl = serverUrl
        return try {
            val r = ApiClient(state.serverUrl).register(deviceInfo(context, state), enrollmentKey.trim())
            when {
                r.code == 201 && r.body != null -> {
                    SecureStore(context).putToken(r.body.getString("device_token"))
                    state.deviceId = r.body.getString("device_id")
                    state.pendingEnrollmentKey = ""
                    null
                }
                r.code == 403 -> "Invalid enrollment key"
                r.code == 409 -> "Already registered on server"
                else -> "Server error ${r.code}"
            }
        } catch (e: Exception) {
            "Cannot reach server: ${e.javaClass.simpleName}"
        }
    }
}

