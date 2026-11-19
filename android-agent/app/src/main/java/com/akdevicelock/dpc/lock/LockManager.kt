package com.akdevicelock.dpc.lock

/** Result of a lock-related operation. Never report success unless the platform call was made. */
sealed class LockResult {
    data object Success : LockResult()
    data class Failure(val reason: String) : LockResult()
}

/**
 * Abstraction over supported lock mechanisms. Implementations:
 *  - DevicePolicyLockManager: lockNow() (one-time screen lock, NOT a persistent financing lock)
 *  - KioskRestrictionManager (planned): Lock Task Mode
 *  - FinancingDeviceLockManager (planned): DeviceLockManager, Android 14+ compatible devices only
 */
interface LockManager {
    val name: String
    fun isSupported(): Boolean
    fun lock(): LockResult
    fun unlock(): LockResult
}

