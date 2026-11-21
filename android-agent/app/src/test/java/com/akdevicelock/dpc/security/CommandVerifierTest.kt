package com.akdevicelock.dpc.security

import com.akdevicelock.dpc.commands.Command
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.security.KeyPairGenerator
import java.security.Signature
import java.security.spec.ECGenParameterSpec
import java.util.Base64
import java.util.UUID

class CommandVerifierTest {

    private fun generateKeyPair() = KeyPairGenerator.getInstance("EC").apply {
        initialize(ECGenParameterSpec("secp256r1"))
    }.generateKeyPair()

    private fun sign(cmd: Command, privateKey: java.security.PrivateKey): Command {
        val sig = Signature.getInstance("SHA256withECDSA").run {
            initSign(privateKey)
            update(CommandVerifier.canonical(cmd))
            Base64.getEncoder().encodeToString(sign())
        }
        return cmd.copy(signature = sig)
    }

    private fun baseCmd(deviceId: String, now: Long, type: String = "DEVICE_LOCK") = Command(
        commandId = UUID.randomUUID().toString(),
        deviceId = deviceId,
        commandType = type,
        issuedAt = now - 10,
        expiresAt = now + 3600,
        nonce = "0123456789abcdef",
        keyId = UUID.randomUUID().toString(),
        signature = "",
        reason = "test",
    )

    @Test
    fun validCommandPassesVerification() {
        val kp = generateKeyPair()
        val pubB64 = Base64.getEncoder().encodeToString(kp.public.encoded)
        val devId = UUID.randomUUID().toString()
        val now = 1_700_000_000L
        val cmd = sign(baseCmd(devId, now), kp.private)
        assertNull(verifyPureJvm(pubB64, cmd, devId, now))
    }

    @Test
    fun rejectsExpiredCommand() {
        val kp = generateKeyPair()
        val pubB64 = Base64.getEncoder().encodeToString(kp.public.encoded)
        val devId = UUID.randomUUID().toString()
        val now = 1_700_000_000L
        val cmd = sign(baseCmd(devId, now).copy(expiresAt = now - 1), kp.private)
        assertEquals("expired", verifyPureJvm(pubB64, cmd, devId, now))
    }

    @Test
    fun rejectsWrongDevice() {
        val kp = generateKeyPair()
        val pubB64 = Base64.getEncoder().encodeToString(kp.public.encoded)
        val devId = UUID.randomUUID().toString()
        val now = 1_700_000_000L
        val cmd = sign(baseCmd(UUID.randomUUID().toString(), now), kp.private)
        assertEquals("wrong_device", verifyPureJvm(pubB64, cmd, devId, now))
    }

    @Test
    fun telemetryAndPolicyCommandTypesPassVerification() {
        val kp = generateKeyPair()
        val pubB64 = Base64.getEncoder().encodeToString(kp.public.encoded)
        val devId = UUID.randomUUID().toString()
        val now = 1_700_000_000L
        for (cmdType in listOf(
            "DEVICE_LOCATE",
            "DEVICE_PHOTO",
            "DEVICE_CAMERA_OFF",
            "DEVICE_CAMERA_ON",
            "DEVICE_GPS_ON",
            "DEVICE_GPS_UNLOCK",
            "DEVICE_NET_LOCK",
            "DEVICE_NET_UNLOCK",
        )) {
            val cmd = sign(baseCmd(devId, now, type = cmdType), kp.private)
            assertNull(verifyPureJvm(pubB64, cmd, devId, now))
        }
    }

    @Test
    fun rejectsUnauthorizedCommandType() {
        val kp = generateKeyPair()
        val pubB64 = Base64.getEncoder().encodeToString(kp.public.encoded)
        val devId = UUID.randomUUID().toString()
        val now = 1_700_000_000L
        val cmd = sign(baseCmd(devId, now, type = "SHELL_EXEC"), kp.private)
        assertEquals("unauthorized_command_type", verifyPureJvm(pubB64, cmd, devId, now))
    }

    @Test
    fun rejectsTamperedSignature() {
        val kp = generateKeyPair()
        val pubB64 = Base64.getEncoder().encodeToString(kp.public.encoded)
        val devId = UUID.randomUUID().toString()
        val now = 1_700_000_000L
        val cmd = sign(baseCmd(devId, now), kp.private).copy(reason = "tampered")
        assertEquals("invalid_signature", verifyPureJvm(pubB64, cmd, devId, now))
    }

    private fun verifyPureJvm(pubB64: String, c: Command, myDevId: String, now: Long): String? {
        if (c.commandType !in CommandVerifier.ALLOWED_TYPES) return "unauthorized_command_type"
        if (c.deviceId != myDevId) return "wrong_device"
        if (c.expiresAt <= now) return "expired"
        val pub = java.security.KeyFactory.getInstance("EC")
            .generatePublic(java.security.spec.X509EncodedKeySpec(Base64.getDecoder().decode(pubB64)))
        val ok = Signature.getInstance("SHA256withECDSA").run {
            initVerify(pub)
            update(CommandVerifier.canonical(c))
            verify(Base64.getDecoder().decode(c.signature))
        }
        return if (ok) null else "invalid_signature"
    }
}

