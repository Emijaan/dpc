package com.akdevicelock.dpc.commands

import android.content.Context
import org.json.JSONObject

/** Non-secret app state stored in Device-Protected Storage so it works during Direct Boot. */
class AppState(context: Context) {
    private val dpContext = context.applicationContext.createDeviceProtectedStorageContext()
    private val prefs = dpContext.getSharedPreferences("app_state_dp", Context.MODE_PRIVATE)

    var serverUrl: String
        get() = prefs.getString("server_url", "") ?: ""
        set(v) = prefs.edit().putString("server_url", v.trim().trimEnd('/')).apply()

    var deviceId: String
        get() = prefs.getString("device_id", "") ?: ""
        set(v) = prefs.edit().putString("device_id", v).apply()

    val isRegistered get() = deviceId.isNotEmpty()

    /** Enrollment key delivered by QR provisioning; cleared as soon as registration succeeds. */
    var pendingEnrollmentKey: String
        get() = prefs.getString("pending_key", "") ?: ""
        set(v) = prefs.edit().putString("pending_key", v).apply()

    val installationId: String
        get() = prefs.getString("installation_id", null) ?: java.util.UUID.randomUUID().toString().also {
            prefs.edit().putString("installation_id", it).apply()
        }

    /** server_time - local_time (seconds), so expiry is judged on server time, not a skewed phone clock. */
    var serverOffset: Long
        get() = prefs.getLong("server_offset", 0)
        set(v) = prefs.edit().putLong("server_offset", v).apply()

    var lastSync: Long
        get() = prefs.getLong("last_sync", 0)
        set(v) = prefs.edit().putLong("last_sync", v).apply()

    var connection: String
        get() = prefs.getString("connection", "unknown") ?: "unknown"
        set(v) = prefs.edit().putString("connection", v).apply()

    var lastCommand: String
        get() = prefs.getString("last_command", "none") ?: "none"
        set(v) = prefs.edit().putString("last_command", v).apply()

    var emiAmount: String
        get() = prefs.getString("emi_amount", "") ?: ""
        set(v) = prefs.edit().putString("emi_amount", v).apply()

    var emiDueDate: String
        get() = prefs.getString("emi_due_date", "") ?: ""
        set(v) = prefs.edit().putString("emi_due_date", v).apply()

    var pendingEmiCount: String
        get() = prefs.getString("pending_emi_count", "") ?: ""
        set(v) = prefs.edit().putString("pending_emi_count", v).apply()

    var dealerName: String
        get() = prefs.getString("dealer_name", "") ?: ""
        set(v) = prefs.edit().putString("dealer_name", v).apply()

    var dealerMobile: String
        get() = prefs.getString("dealer_mobile", "") ?: ""
        set(v) = prefs.edit().putString("dealer_mobile", v).apply()

    var dealerCompany: String
        get() = prefs.getString("dealer_company", "") ?: ""
        set(v) = prefs.edit().putString("dealer_company", v).apply()

    var frpAccountsCsv: String
        get() = prefs.getString("frp_accounts", "") ?: ""
        set(v) = prefs.edit().putString("frp_accounts", v).apply()

    var frpConfiguredFromServer: Boolean
        get() = prefs.getBoolean("frp_server_configured", false)
        set(v) = prefs.edit().putBoolean("frp_server_configured", v).apply()

    fun updateFrpAccounts(arr: org.json.JSONArray?): Boolean {
        if (arr == null) return false
        val ids = mutableListOf<String>()
        for (i in 0 until arr.length()) {
            val s = arr.optString(i, "").trim()
            if (isValidFrpAccountId(s) && s !in ids) ids.add(s)
        }
        val csv = ids.joinToString(",")
        val changed = csv != frpAccountsCsv || !frpConfiguredFromServer
        prefs.edit()
            .putString("frp_accounts", csv)
            .putBoolean("frp_server_configured", true)
            .apply()
        return changed
    }

    fun frpAccountList(defaultCsv: String): List<String> {
        val raw = if (frpConfiguredFromServer) frpAccountsCsv else frpAccountsCsv.ifBlank { defaultCsv }
        return raw.split(",").map { it.trim() }.filter { isValidFrpAccountId(it) }.distinct()
    }

    companion object {
        fun isValidFrpAccountId(id: String): Boolean =
            id.length == 21 && id.all { it in '0'..'9' }
    }

    fun updateLockScreenInfo(obj: JSONObject?) {
        if (obj == null) return
        fun clean(key: String) = if (obj.isNull(key)) "" else obj.optString(key, "").trim()
        prefs.edit()
            .putString("emi_amount", clean("emi_amount"))
            .putString("emi_due_date", clean("emi_due_date"))
            .putString("pending_emi_count", clean("pending_emi_count"))
            .putString("dealer_name", clean("dealer_name"))
            .putString("dealer_mobile", clean("dealer_mobile"))
            .putString("dealer_company", clean("dealer_company"))
            .apply()
    }

    var lastTokenRenewal: Long
        get() = prefs.getLong("last_token_renewal", 0)
        set(v) = prefs.edit().putLong("last_token_renewal", v).apply()

    var deviceKeyRegistered: Boolean
        get() = prefs.getBoolean("device_key_registered", false)
        set(v) = prefs.edit().putBoolean("device_key_registered", v).apply()

    fun updateKeyBundle(validKeys: Map<String, String>, revokedIds: Set<String>) {
        val m = JSONObject()
        validKeys.forEach { (k, v) -> m.put(k, v) }
        val r = org.json.JSONArray()
        revokedIds.forEach { r.put(it) }
        prefs.edit().putString("valid_keys", m.toString()).putString("revoked_keys", r.toString()).apply()
    }

    fun getPublicKeyForId(keyId: String): String? {
        val m = JSONObject(prefs.getString("valid_keys", "{}")!!)
        return m.optString(keyId, "").ifEmpty { null }
    }

    fun hasKeyBundle(): Boolean = JSONObject(prefs.getString("valid_keys", "{}")!!).length() > 0

    fun isKeyRevoked(keyId: String): Boolean {
        val arr = org.json.JSONArray(prefs.getString("revoked_keys", "[]")!!)
        for (i in 0 until arr.length()) {
            if (arr.optString(i) == keyId) return true
        }
        return false
    }

    fun nowServerSeconds() = System.currentTimeMillis() / 1000 + serverOffset

    // ---- replay protection: processed command ids -> result, and seen nonces ----
    fun processed(commandId: String): JSONObject? =
        JSONObject(prefs.getString("processed", "{}")!!).optJSONObject(commandId)

    fun nonceSeen(nonce: String) = JSONObject(prefs.getString("nonces", "{}")!!).has(nonce)

    fun recordProcessed(commandId: String, nonce: String, ok: Boolean, result: String) {
        val p = JSONObject(prefs.getString("processed", "{}")!!)
        p.put(commandId, JSONObject().put("ok", ok).put("result", result).put("ts", System.currentTimeMillis()))
        val n = JSONObject(prefs.getString("nonces", "{}")!!).put(nonce, System.currentTimeMillis())
        prefs.edit().putString("processed", prune(p)).putString("nonces", prune(n)).apply()
    }

    private fun prune(o: JSONObject): String {
        val keys = o.keys().asSequence().toList()
        if (keys.size > 500) {
            keys.sortedBy { (o.get(it) as? JSONObject)?.optLong("ts") ?: o.optLong(it) }
                .take(keys.size - 500).forEach { o.remove(it) }
        }
        return o.toString()
    }

    fun reset() { prefs.edit().clear().apply() }
}

