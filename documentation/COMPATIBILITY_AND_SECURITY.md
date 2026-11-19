# AK DeviceLock Compatibility, Architecture & Security Report

## 1. Supported Lock Implementations

| Implementation | Android API | Persistence | Remote Unlock | Notes |
|---|---|---|---|---|
| `DevicePolicyLockManager` | `DevicePolicyManager.lockNow()` | One-time screen lock | Not applicable (user unlocks with own PIN/pattern) | Tested on Vivo 1902 (Android 9) |
| `KioskRestrictionManager` | `setLockTaskPackages()`, `setLockTaskFeatures()`, `startLockTask()` | Persistent across activity resumes and device reboot (`BootReceiver`) | Supported (`DEVICE_UNLOCK` clears lock-task whitelist and stops lock task) | Preserves emergency dialer (`tel:112`). Tested on Vivo 1902 (Android 9) |
| `FinancingDeviceLockManager` | Android 14+ `DeviceLockManager` | Separate financing role (OEM/Google partner program) | Requires financing role eligibility | Documented for future evaluation; not assumed on standard devices |

## 2. Security Architecture

- **Command Signing**: All server commands (`DEVICE_LOCK`, `DEVICE_UNLOCK`, `DEVICE_STATUS`, `DEVICE_SYNC`, `DEVICE_RELEASE`) are signed using **ECDSA P-256 (`SHA256withECDSA`)** over the canonical payload `command_id|device_id|command_type|issued_at|expires_at|nonce|reason`.
- **Android Verification**: `CommandVerifier` validates command type, UUID structure, device ID binding, server-relative clock expiration, and ECDSA signature against the embedded X.509 public key before executing any operation.
- **Replay & Duplicate Protection**: Both the backend and Android agent enforce idempotency and track processed `command_id`s and `nonce`s.
- **Credential Storage**: Device authentication tokens are hashed (`SHA-256`) at rest in the backend database and encrypted with a non-exportable **Android Keystore AES-256-GCM** key (`SecureStore`) on the device.
- **Truthful State Reporting**: The backend never flips a device's `restriction_status` to `LOCKED` or `NONE` when a command is created; state changes only when the device reports `EXECUTED` via `/api/v1/commands/acknowledge/`.

## 3. Known Hardware & OS Realities

- **Hardware Recovery Reset**: If a user powers off the device and performs a hardware key-combination wipe from the bootloader/recovery menu, Android OS is not running and no DPC can block it. Protection against recovery wipe relies on Google Factory Reset Protection (FRP), Zero-Touch Enrollment, or Samsung Knox Guard.
- **QR Provisioning**: On factory-reset Android 9+ devices, tapping the welcome screen 6 times launches the built-in QR reader. Scanning `/panel/qr/` downloads the signed APK, verifies `PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM`, sets `AkDeviceAdminReceiver` as Device Owner, passes `server_url` and `enrollment_key` via `PROVISIONING_ADMIN_EXTRAS_BUNDLE`, and auto-registers the device.

