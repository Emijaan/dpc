package com.akdevicelock.dpc.commands

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageInstaller
import android.content.pm.PackageManager
import android.os.Build
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * Downloads, signature-verifies, and silently installs self-updates via Device Owner PackageInstaller.
 */
object AppUpdater {
    private const val STAGED_NAME = "pending_update.apk"

    fun stagedFile(context: Context): File = File(context.cacheDir, STAGED_NAME)

    fun prepareUpdate(context: Context, serverUrl: String): Pair<Boolean, String> {
        val base = serverUrl.trim().trimEnd('/')
        if (base.isEmpty()) return false to "server URL missing"
        val outFile = stagedFile(context)
        if (outFile.exists()) outFile.delete()
        return try {
            downloadWithRedirects("$base/download/akdevicelock.apk", outFile)
            verifyApk(context, outFile)
        } catch (e: Exception) {
            outFile.delete()
            false to "update download failed: ${e.javaClass.simpleName}"
        }
    }

    fun installPreparedUpdate(context: Context): Boolean {
        val apkFile = stagedFile(context)
        if (!apkFile.exists() || apkFile.length() == 0L) return false
        return try {
            val pi = context.packageManager.packageInstaller
            val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL).apply {
                setAppPackageName(context.packageName)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED)
                }
            }
            val sessionId = pi.createSession(params)
            val session = pi.openSession(sessionId)
            session.use { s ->
                s.openWrite("akdl_update.apk", 0, apkFile.length()).use { out ->
                    apkFile.inputStream().use { input -> input.copyTo(out) }
                    s.fsync(out)
                }
                val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
                val callbackIntent = Intent(context, UpdateReceiver::class.java).setPackage(context.packageName)
                val statusIntent = PendingIntent.getBroadcast(context, sessionId, callbackIntent, flags)
                s.commit(statusIntent.intentSender)
            }
            true
        } catch (e: Exception) {
            AppState(context).lastCommand = "DEVICE_UPDATE commit error: ${e.message}"
            apkFile.delete()
            false
        }
    }

    private fun downloadWithRedirects(startUrl: String, outFile: File) {
        var current = startUrl
        repeat(5) {
            val conn = (URL(current).openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = 15_000
                readTimeout = 60_000
                instanceFollowRedirects = true
            }
            try {
                val code = conn.responseCode
                if (code in 300..399) {
                    val loc = conn.getHeaderField("Location") ?: error("redirect missing Location")
                    current = URL(URL(current), loc).toString()
                    return@repeat
                }
                if (code !in 200..299) error("HTTP $code")
                conn.inputStream.use { input ->
                    outFile.outputStream().use { out -> input.copyTo(out) }
                }
                return
            } finally {
                conn.disconnect()
            }
        }
        error("too many redirects")
    }

    @Suppress("DEPRECATION")
    private fun verifyApk(context: Context, apkFile: File): Pair<Boolean, String> {
        if (!apkFile.exists() || apkFile.length() < 10_000L) {
            apkFile.delete()
            return false to "invalid APK size"
        }
        val pm = context.packageManager
        val flags = PackageManager.GET_SIGNING_CERTIFICATES
        val archiveInfo: PackageInfo = pm.getPackageArchiveInfo(apkFile.absolutePath, flags)
            ?: run {
                apkFile.delete()
                return false to "unparseable APK"
            }
        if (archiveInfo.packageName != context.packageName) {
            apkFile.delete()
            return false to "package mismatch: ${archiveInfo.packageName}"
        }
        val currentInfo = pm.getPackageInfo(context.packageName, flags)
        val currentDigests = signerSha256Set(currentInfo)
        val newDigests = signerSha256Set(archiveInfo)
        if (currentDigests.isEmpty() || newDigests.none { it in currentDigests }) {
            apkFile.delete()
            return false to "signing certificate mismatch"
        }
        if (archiveInfo.longVersionCode < currentInfo.longVersionCode) {
            apkFile.delete()
            return false to "version downgrade blocked (${archiveInfo.longVersionCode} < ${currentInfo.longVersionCode})"
        }
        return true to "verified v${archiveInfo.versionName} (${archiveInfo.longVersionCode}); installing"
    }

    @Suppress("DEPRECATION")
    private fun signerSha256Set(info: PackageInfo): Set<String> {
        val signers = info.signingInfo?.apkContentsSigners ?: return emptySet()
        val md = MessageDigest.getInstance("SHA-256")
        return signers.map { sig ->
            md.digest(sig.toByteArray()).joinToString("") { "%02x".format(it) }
        }.toSet()
    }
}
