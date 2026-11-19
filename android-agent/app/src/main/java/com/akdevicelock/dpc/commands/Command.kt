package com.akdevicelock.dpc.commands

import org.json.JSONObject

data class Command(
    val commandId: String,
    val deviceId: String,
    val commandType: String,
    val issuedAt: Long,
    val expiresAt: Long,
    val nonce: String,
    val keyId: String,
    val signature: String,
    val reason: String,
) {
    companion object {
        fun parse(o: JSONObject): Command? = try {
            Command(
                o.getString("command_id"),
                o.getString("device_id"),
                o.getString("command_type"),
                o.getLong("issued_at"),
                o.getLong("expires_at"),
                o.getString("nonce"),
                o.optString("key_id", ""),
                o.getString("signature"),
                o.optString("reason", ""),
            )
        } catch (e: Exception) { null }
    }
}
