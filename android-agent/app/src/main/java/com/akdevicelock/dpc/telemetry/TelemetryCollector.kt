package com.akdevicelock.dpc.telemetry

import android.Manifest
import android.annotation.SuppressLint
import android.app.admin.DevicePolicyManager
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ImageFormat
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.media.ImageReader
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.os.Looper
import android.os.UserManager
import android.telephony.TelephonyManager
import android.util.Base64
import com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.Inet4Address
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Collects GPS location, network telemetry, and camera snapshots, and manages
 * Device Owner access/policy controls for Camera, GPS/Location, and Network settings.
 */
object TelemetryCollector {

    data class GpsFix(
        val latitude: Double,
        val longitude: Double,
        val accuracy: Float?,
    )

    data class NetworkInfo(
        val networkType: String,
        val wifiSsid: String,
        val networkOperator: String,
        val ipAddress: String,
    )

    fun hasPermission(context: Context, perm: String): Boolean =
        context.checkSelfPermission(perm) == PackageManager.PERMISSION_GRANTED

    @SuppressLint("MissingPermission")
    fun collectLocation(context: Context, forceFresh: Boolean = false): GpsFix? {
        if (!hasPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) &&
            !hasPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION)
        ) {
            return null
        }
        val lm = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        if (forceFresh) {
            requestFreshLocation(context, lm)?.let {
                return GpsFix(it.latitude, it.longitude, if (it.hasAccuracy()) it.accuracy else null)
            }
        }
        val providers = listOf(
            LocationManager.GPS_PROVIDER,
            LocationManager.NETWORK_PROVIDER,
            LocationManager.PASSIVE_PROVIDER,
        )
        var best: Location? = null
        for (p in providers) {
            val loc = try {
                if (lm.isProviderEnabled(p)) lm.getLastKnownLocation(p) else null
            } catch (_: Exception) {
                null
            } ?: continue
            if (best == null || loc.time > best.time) {
                best = loc
            }
        }
        return best?.let { GpsFix(it.latitude, it.longitude, if (it.hasAccuracy()) it.accuracy else null) }
    }

    @SuppressLint("MissingPermission")
    private fun requestFreshLocation(context: Context, lm: LocationManager): Location? {
        val provider = when {
            lm.isProviderEnabled(LocationManager.GPS_PROVIDER) -> LocationManager.GPS_PROVIDER
            lm.isProviderEnabled(LocationManager.NETWORK_PROVIDER) -> LocationManager.NETWORK_PROVIDER
            else -> return null
        }
        val latch = CountDownLatch(1)
        var result: Location? = null
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            try {
                lm.getCurrentLocation(provider, null, context.mainExecutor) { loc ->
                    result = loc
                    latch.countDown()
                }
                latch.await(8, TimeUnit.SECONDS)
                return result
            } catch (_: Exception) {
            }
        }
        val ht = HandlerThread("akdl-gps").apply { start() }
        return try {
            @Suppress("DEPRECATION")
            lm.requestSingleUpdate(provider, object : LocationListener {
                override fun onLocationChanged(location: Location) {
                    result = location
                    latch.countDown()
                }
                @Deprecated("Deprecated in Java")
                override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) {}
                override fun onProviderEnabled(provider: String) {}
                override fun onProviderDisabled(provider: String) {}
            }, ht.looper)
            latch.await(8, TimeUnit.SECONDS)
            result
        } catch (_: Exception) {
            null
        } finally {
            ht.quitSafely()
        }
    }

    @Suppress("DEPRECATION")
    fun collectNetwork(context: Context): NetworkInfo {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val net = cm.activeNetwork
        val caps = net?.let { cm.getNetworkCapabilities(it) }
        val netType = when {
            caps == null -> "OFFLINE"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "WIFI"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "CELLULAR"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ETHERNET"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN) -> "VPN"
            else -> "OTHER"
        }
        var ip = ""
        try {
            val lp = net?.let { cm.getLinkProperties(it) }
            ip = lp?.linkAddresses
                ?.map { it.address }
                ?.firstOrNull { it is Inet4Address && !it.isLoopbackAddress }
                ?.hostAddress.orEmpty()
        } catch (_: Exception) {
        }
        var ssid = ""
        if (netType == "WIFI" &&
            (hasPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ||
                hasPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION))
        ) {
            try {
                val wm = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
                val raw = wm.connectionInfo?.ssid.orEmpty().trim('"')
                if (raw.isNotEmpty() && raw != "<unknown ssid>") ssid = raw.take(64)
            } catch (_: Exception) {
            }
        }
        var operator = ""
        try {
            val tm = context.getSystemService(Context.TELEPHONY_SERVICE) as TelephonyManager
            operator = (tm.networkOperatorName ?: "").take(64)
        } catch (_: Exception) {
        }
        return NetworkInfo(netType, ssid, operator, ip)
    }

    fun appendTelemetry(context: Context, payload: JSONObject, forceFreshGps: Boolean = false) {
        val net = collectNetwork(context)
        payload.put("network_type", net.networkType)
        payload.put("wifi_ssid", net.wifiSsid)
        payload.put("network_operator", net.networkOperator)
        payload.put("ip_address", net.ipAddress)

        collectLocation(context, forceFreshGps)?.let { fix ->
            payload.put("latitude", fix.latitude)
            payload.put("longitude", fix.longitude)
            fix.accuracy?.let { payload.put("location_accuracy", it.toDouble()) }
        }

        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        val um = context.getSystemService(Context.USER_SERVICE) as UserManager
        val admin = AkDeviceAdminReceiver.component(context)
        val camDisabled = try {
            if (dpm.isDeviceOwnerApp(context.packageName)) dpm.getCameraDisabled(admin) else false
        } catch (_: Exception) { false }
        payload.put("camera_disabled", camDisabled)
        payload.put("gps_forced_on", um.hasUserRestriction(UserManager.DISALLOW_CONFIG_LOCATION))
        payload.put(
            "network_restricted",
            um.hasUserRestriction(UserManager.DISALLOW_CONFIG_WIFI) ||
                um.hasUserRestriction(UserManager.DISALLOW_CONFIG_MOBILE_NETWORKS)
        )
    }

    fun setCameraDisabled(context: Context, disabled: Boolean): Pair<Boolean, String> {
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        if (!dpm.isDeviceOwnerApp(context.packageName)) return false to "not device owner"
        return try {
            dpm.setCameraDisabled(AkDeviceAdminReceiver.component(context), disabled)
            true to if (disabled) "camera disabled" else "camera enabled"
        } catch (e: Exception) {
            false to "camera policy failed: ${e.message ?: e.javaClass.simpleName}"
        }
    }

    fun setGpsPolicy(context: Context, forceOnAndLock: Boolean): Pair<Boolean, String> {
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        if (!dpm.isDeviceOwnerApp(context.packageName)) return false to "not device owner"
        val admin = AkDeviceAdminReceiver.component(context)
        return try {
            if (forceOnAndLock) {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    dpm.setLocationEnabled(admin, true)
                }
                dpm.addUserRestriction(admin, UserManager.DISALLOW_CONFIG_LOCATION)
                true to "gps enabled and locked"
            } else {
                dpm.clearUserRestriction(admin, UserManager.DISALLOW_CONFIG_LOCATION)
                true to "gps setting unlocked"
            }
        } catch (e: Exception) {
            false to "gps policy failed: ${e.message ?: e.javaClass.simpleName}"
        }
    }

    fun setNetworkRestricted(context: Context, restrict: Boolean): Pair<Boolean, String> {
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        if (!dpm.isDeviceOwnerApp(context.packageName)) return false to "not device owner"
        val admin = AkDeviceAdminReceiver.component(context)
        val keys = listOf(
            UserManager.DISALLOW_CONFIG_WIFI,
            UserManager.DISALLOW_CONFIG_MOBILE_NETWORKS,
            UserManager.DISALLOW_CONFIG_TETHERING,
            UserManager.DISALLOW_AIRPLANE_MODE,
        )
        return try {
            for (k in keys) {
                if (restrict) dpm.addUserRestriction(admin, k)
                else dpm.clearUserRestriction(admin, k)
            }
            true to if (restrict) "network settings locked" else "network settings unlocked"
        } catch (e: Exception) {
            false to "network policy failed: ${e.message ?: e.javaClass.simpleName}"
        }
    }

    @SuppressLint("MissingPermission")
    fun capturePhotoJpegB64(context: Context): Pair<String?, String> {
        if (!hasPermission(context, Manifest.permission.CAMERA)) {
            return null to "CAMERA permission not granted"
        }
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        if (dpm.isDeviceOwnerApp(context.packageName)) {
            try {
                if (dpm.getCameraDisabled(AkDeviceAdminReceiver.component(context))) {
                    return null to "camera is disabled by policy"
                }
            } catch (_: Exception) {}
        }
        val direct = captureDirectCamera2(context)
        if (!direct.first.isNullOrEmpty()) return direct
        if (direct.second.contains("camera error 4") || direct.second.contains("background")) {
            return PhotoCaptureActivity.captureViaForegroundActivity(context)
        }
        return direct
    }

    @SuppressLint("MissingPermission")
    internal fun captureDirectCamera2(context: Context): Pair<String?, String> {
        if (!hasPermission(context, Manifest.permission.CAMERA)) {
            return null to "CAMERA permission not granted"
        }
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        if (dpm.isDeviceOwnerApp(context.packageName)) {
            try {
                if (dpm.getCameraDisabled(AkDeviceAdminReceiver.component(context))) {
                    return null to "camera is disabled by policy"
                }
            } catch (_: Exception) {}
        }

        val cm = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val camId = try {
            cm.cameraIdList.firstOrNull { id ->
                cm.getCameraCharacteristics(id).get(CameraCharacteristics.LENS_FACING) ==
                    CameraCharacteristics.LENS_FACING_FRONT
            } ?: cm.cameraIdList.firstOrNull()
        } catch (e: Exception) {
            return null to "no camera available: ${e.message}"
        } ?: return null to "no camera available"

        val ht = HandlerThread("akdl-cam").apply { start() }
        val handler = Handler(ht.looper)
        val reader = ImageReader.newInstance(640, 480, ImageFormat.JPEG, 2)
        val latch = CountDownLatch(1)
        var b64Result: String? = null
        var errMsg = "camera capture timed out"
        var openedDevice: CameraDevice? = null

        reader.setOnImageAvailableListener({ r ->
            val img = try { r.acquireLatestImage() } catch (_: Exception) { null }
            if (img != null) {
                try {
                    val buf = img.planes[0].buffer
                    val rawBytes = ByteArray(buf.remaining())
                    buf.get(rawBytes)
                    b64Result = compressJpegToB64(rawBytes)
                    errMsg = "captured"
                } catch (e: Exception) {
                    errMsg = "encode failed: ${e.message}"
                } finally {
                    img.close()
                    latch.countDown()
                }
            }
        }, handler)

        try {
            cm.openCamera(camId, object : CameraDevice.StateCallback() {
                override fun onOpened(camera: CameraDevice) {
                    openedDevice = camera
                    try {
                        @Suppress("DEPRECATION")
                        camera.createCaptureSession(
                            listOf(reader.surface),
                            object : CameraCaptureSession.StateCallback() {
                                override fun onConfigured(session: CameraCaptureSession) {
                                    try {
                                        val req = camera.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE).apply {
                                            addTarget(reader.surface)
                                            set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE)
                                            set(CaptureRequest.JPEG_QUALITY, 70.toByte())
                                        }
                                        session.capture(req.build(), null, handler)
                                    } catch (e: Exception) {
                                        errMsg = "capture failed: ${e.message}"
                                        latch.countDown()
                                    }
                                }
                                override fun onConfigureFailed(session: CameraCaptureSession) {
                                    errMsg = "camera session config failed"
                                    latch.countDown()
                                }
                            },
                            handler
                        )
                    } catch (e: Exception) {
                        errMsg = "session error: ${e.message}"
                        latch.countDown()
                    }
                }
                override fun onDisconnected(camera: CameraDevice) {
                    errMsg = "camera disconnected"
                    latch.countDown()
                }
                override fun onError(camera: CameraDevice, error: Int) {
                    errMsg = "camera error $error"
                    latch.countDown()
                }
            }, handler)
            latch.await(10, TimeUnit.SECONDS)
        } catch (e: Exception) {
            errMsg = "openCamera failed: ${e.message ?: e.javaClass.simpleName}"
        } finally {
            try { openedDevice?.close() } catch (_: Exception) {}
            try { reader.close() } catch (_: Exception) {}
            ht.quitSafely()
        }
        return b64Result to errMsg
    }

    private fun compressJpegToB64(rawBytes: ByteArray): String {
        val bmp = BitmapFactory.decodeByteArray(rawBytes, 0, rawBytes.size)
            ?: return Base64.encodeToString(rawBytes, Base64.NO_WRAP)
        val out = ByteArrayOutputStream()
        bmp.compress(Bitmap.CompressFormat.JPEG, 65, out)
        bmp.recycle()
        return Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
    }
}
