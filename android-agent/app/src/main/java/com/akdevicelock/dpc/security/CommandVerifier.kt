package com.akdevicelock.dpc.security

import android.content.Context
import android.util.Base64
import com.akdevicelock.dpc.R
import com.akdevicelock.dpc.commands.AppState
import com.akdevicelock.dpc.commands.Command
import java.security.KeyFactory
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import java.util.UUID

/** Validates a command against distributed public keys, revocation lists, expiry, and device binding. */
object CommandVerifier {
    val ALLOWED_TYPES = setOf(
        "DEVICE_LOCK",
        "DEVICE_UNLOCK",
        "DEVICE_STATUS",
        "DEVICE_SYNC",
        "DEVICE_LOCATE",
        "DEVICE_PHOTO",
        "DEVICE_CAMERA_OFF",
        "DEVICE_CAMERA_ON",
        "DEVICE_GPS_ON",
        "DEVICE_GPS_UNLOCK",
        "DEVICE_NET_LOCK",
        "DEVICE_NET_UNLOCK",
        "DEVICE_RELEASE",
    )
    private const val MAX_TTL = 7L * 24 * 3600
    private const val MAX_CLOCK_SKEW = 300L

    fun canonical(c: Command): ByteArray {
        val fields = mutableListOf(
            c.commandId, c.deviceId, c.commandType,
            c.issuedAt.toString(), c.expiresAt.toString(),
            c.nonce, c.reason
        )
        if (c.keyId.isNotEmpty()) fields.add(c.keyId)
        return fields.joinToString("|").toByteArray(Charsets.UTF_8)
    }

    fun verify(context: Context, c: Command, myDeviceId: String, nowSeconds: Long): String? {
        val state = AppState(context)
        if (c.keyId.isNotEmpty() && state.isKeyRevoked(c.keyId)) return "revoked_key"
        val pubB64 = when {
            c.keyId.isNotEmpty() -> state.getPublicKeyForId(c.keyId)
                ?: if (!state.hasKeyBundle()) context.getString(R.string.command_public_key) else return "unknown_key"
            else -> context.getString(R.string.command_public_key)
        }
        return verifyWithKey(pubB64, c, myDeviceId, nowSeconds)
    }

    fun verifyWithKey(publicKeyB64: String, c: Command, myDeviceId: String, nowSeconds: Long): String? {
        if (c.commandType !in ALLOWED_TYPES) return "unauthorized_command_type"
        if (!isUuid(c.commandId) || !isUuid(c.deviceId)) return "invalid_payload"
        if (c.nonce.length !in 8..64 || c.reason.length > 200) return "invalid_payload"
        if (c.deviceId != myDeviceId) return "wrong_device"
        if (c.expiresAt <= c.issuedAt || c.expiresAt - c.issuedAt > MAX_TTL) return "invalid_payload"
        if (c.issuedAt > nowSeconds + MAX_CLOCK_SKEW) return "issued_in_future"
        if (c.expiresAt <= nowSeconds) return "expired"
        return if (signatureValid(publicKeyB64, c)) null else "invalid_signature"
    }

    private fun isUuid(s: String) = try { UUID.fromString(s); true } catch (e: Exception) { false }

    private fun signatureValid(publicKeyB64: String, c: Command): Boolean = try {
        val decodedPub = Base64.decode(publicKeyB64, Base64.DEFAULT)
        val decodedSig = Base64.decode(c.signature, Base64.DEFAULT)
        val pub = KeyFactory.getInstance("EC").generatePublic(X509EncodedKeySpec(decodedPub))
        Signature.getInstance("SHA256withECDSA").run {
            initVerify(pub)
            update(canonical(c))
            verify(decodedSig)
        }
    } catch (e: Exception) { false }
}
