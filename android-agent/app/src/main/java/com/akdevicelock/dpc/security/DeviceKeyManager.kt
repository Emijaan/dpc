package com.akdevicelock.dpc.security

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.spec.ECGenParameterSpec

/**
 * Generates and stores a device-unique ECDSA P-256 key pair inside Android Keystore.
 * The private key never leaves hardware/Keystore; only the X.509 public key is exported
 * and registered with the backend keymanagement service.
 */
object DeviceKeyManager {
    private const val ALIAS = "akdl_device_identity_key"

    fun getOrCreatePublicKeyB64(): String? = try {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        if (!ks.containsAlias(ALIAS)) {
            val kpg = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore")
            kpg.initialize(
                KeyGenParameterSpec.Builder(
                    ALIAS,
                    KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY
                )
                    .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
                    .setDigests(KeyProperties.DIGEST_SHA256)
                    .build()
            )
            kpg.generateKeyPair()
        }
        val cert = ks.getCertificate(ALIAS) ?: return null
        Base64.encodeToString(cert.publicKey.encoded, Base64.NO_WRAP)
    } catch (_: Exception) {
        null
    }
}

