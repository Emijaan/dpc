package com.akdevicelock.dpc.networking

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class ApiClient(private val baseUrl: String, private val token: String? = null) {

    class Response(val code: Int, val body: JSONObject?)

    fun request(method: String, path: String, body: JSONObject? = null,
                extraHeaders: Map<String, String> = emptyMap()): Response {
        val conn = URL(baseUrl + path).openConnection() as HttpURLConnection
        try {
            conn.requestMethod = method
            conn.connectTimeout = 10_000
            conn.readTimeout = 15_000
            conn.setRequestProperty("Accept", "application/json")
            token?.let { conn.setRequestProperty("Authorization", "Device $it") }
            extraHeaders.forEach { (k, v) -> conn.setRequestProperty(k, v) }
            if (body != null) {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json")
                conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val code = conn.responseCode
            val stream = if (code >= 400) conn.errorStream else conn.inputStream
            val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            val json = try { JSONObject(text) } catch (e: Exception) { null }
            return Response(code, json)
        } finally {
            conn.disconnect()
        }
    }

    fun register(info: JSONObject, enrollmentKey: String) =
        request("POST", "/api/v1/devices/register/", info, mapOf("X-Enrollment-Key" to enrollmentKey))

    fun sync(info: JSONObject) = request("POST", "/api/v1/devices/sync/", info)
    fun uploadPhoto(photoB64: String) =
        request("POST", "/api/v1/devices/photo/", JSONObject().put("photo_b64", photoB64))
    fun pending() = request("GET", "/api/v1/commands/pending/")
    fun renewToken() = request("POST", "/api/v1/devices/renew-token/", JSONObject())
    fun fetchPublicKeys() = request("GET", "/api/v1/keys/public/")
    fun registerDevicePublicKey(deviceId: String, publicKeyB64: String) =
        request("POST", "/api/v1/devices/$deviceId/keys/register/",
            JSONObject().put("public_key_b64", publicKeyB64).put("algorithm", "ECDSA_P256"))
    fun acknowledge(commandId: String, success: Boolean, result: String) =
        request("POST", "/api/v1/commands/acknowledge/",
            JSONObject().put("command_id", commandId).put("success", success).put("result", result.take(280)))
}

