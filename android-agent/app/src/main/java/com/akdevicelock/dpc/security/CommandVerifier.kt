package com.akdevicelock.dpc.security

import android.content.Context
import android.util.Base64
import com.akdevicelock.dpc.R
import com.akdevicelock.dpc.commands.Command
import java.security.KeyFactory
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import java.util.UUID

/** Validates a command. Returns null when valid, otherwise the rejection reason. */
object CommandVerifier {
    val ALLOWED_TYPES = setOf("DEVICE_LOCK", "DEVICE_UNLOCK", "DEVICE_STATUS", "DEVICE_SYNC", "DEVICE_RELEASE")
    private const val MAX_TTL = 7L * 24 * 3600
    private const val MAX_CLOCK_SKEW = 300L

    fun canonical(c: Command): ByteArray =
        listOf(c.commandId, c.deviceId, c.commandType, c.issuedAt.toString(), c.expiresAt.toString(),
            c.nonce, c.reason).joinToString("|").toByteArray(Charsets.UTF_8)

    fun verify(context: Context, c: Command, myDeviceId: String, nowSeconds: Long): String? {
        if (c.commandType !in ALLOWED_TYPES) return "unauthorized_command_type"
        if (!isUuid(c.commandId) || !isUuid(c.deviceId)) return "invalid_payload"
        if (c.nonce.length !in 8..64 || c.reason.length > 200) return "invalid_payload"
        if (c.deviceId != myDeviceId) return "wrong_device"
        if (c.expiresAt <= c.issuedAt || c.expiresAt - c.issuedAt > MAX_TTL) return "invalid_payload"
        if (c.issuedAt > nowSeconds + MAX_CLOCK_SKEW) return "issued_in_future"
        if (c.expiresAt <= nowSeconds) return "expired"
        return if (signatureValid(context, c)) null else "invalid_signature"
    }

    private fun isUuid(s: String) = try { UUID.fromString(s); true } catch (e: Exception) { false }

    private fun signatureValid(context: Context, c: Command): Boolean = try {
        val pub = KeyFactory.getInstance("EC").generatePublic(
            X509EncodedKeySpec(Base64.decode(context.getString(R.string.command_public_key), Base64.DEFAULT)))
        Signature.getInstance("SHA256withECDSA").run {
            initVerify(pub)
            update(canonical(c))
            verify(Base64.decode(c.signature, Base64.DEFAULT))
        }
    } catch (e: Exception) { false }
}

