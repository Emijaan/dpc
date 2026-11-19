# AK DeviceLock Compatibility, Architecture & Security Report

## 1. Supported Lock Implementations

| Implementation | Android API | Persistence | Remote Unlock | Notes |
|---|---|---|---|---|
| `DevicePolicyLockManager` | `DevicePolicyManager.lockNow()` | One-time screen lock | Not applicable (user unlocks with own PIN/pattern) | Tested on Vivo 1902 (Android 9) |
| `KioskRestrictionManager` | `setLockTaskPackages()`, `setLockTaskFeatures()`, `addPersistentPreferredActivity()` (`LockedHomeAlias`), `setStatusBarDisabled()`, `startLockTask()` | Persistent across activity resumes, Home press, and Direct Boot (`LOCKED_BOOT_COMPLETED`) | Supported (`RemoteUnlockEngine` clears Home alias, status bar block, lock task) | Preserves emergency dialer (`112`) and administrator support call + Wi-Fi enable. Tested on Vivo 1902 (Android 9) and Samsung SM-X115 (Android 16) |
| `FinancingDeviceLockManager` | Android 14+ `DeviceLockManager` (`device_lock` service) | System financing lock (OS-level) | Requires `FINANCING` role + `MANAGE_DEVICE_LOCK_STATE` | Investigated separately: unavailable to standard Device Owner apps on consumer builds; `isSupported()` returns `false` honestly |

## 2. Android Version Provisioning Matrix

| Android Version | Tested / Supported | Recommended Provisioning Method | Notes |
|---|---|---|---|
| **Android 9 – 11** | Tested on Vivo 1902 (Android 9) | **Method B (1-Step Direct QR)** or `provision_usb.bat` | Direct QR installs `akdevicelock.apk` and sets Device Owner in one scan |
| **Android 12 – 15** | Supported | **Method A (2-Step `Test DPC 9.0.12` + `transferOwnership`)** | Bypasses Setup Wizard Play Protect block; `Test DPC 9.0.12` supports ownership transfer and is auto-hidden afterward |
| **Android 16+** | Tested on Samsung `SM-X115` (Android 16, SDK 36) | **`provision_usb.bat`** (0 accounts, Auto Blocker OFF) or KME / Zero-Touch | `Test DPC 9.0.12` crashes in `PostProvisioningTask` on API 36; `Test DPC 9.0.16` disabled `transferOwnership` |

## 3. Security Architecture

- **Command Signing**: All server commands (`DEVICE_LOCK`, `DEVICE_UNLOCK`, `DEVICE_STATUS`, `DEVICE_SYNC`, `DEVICE_RELEASE`) are signed using **ECDSA P-256 (`SHA256withECDSA`)** over `command_id|device_id|command_type|issued_at|expires_at|nonce|reason`.
- **Android Verification**: `CommandVerifier` validates command type, UUIDs, device ID binding, server-relative clock expiration, and ECDSA signature against the embedded X.509 public key before executing any operation.
- **Replay & Duplicate Protection**: Both the backend and Android agent enforce idempotency and track processed `command_id`s and `nonce`s.
- **Credential Storage & Renewal**: Device tokens are SHA-256 hashed at rest in PostgreSQL/SQLite, encrypted with a non-exportable **Android Keystore AES-256-GCM** key (`SecureStore`) in Device-Protected Storage, and automatically rotated every 7 days via `/api/v1/devices/renew-token/`.
- **FCM Wakeup**: `notifications/services.py` implements Firebase HTTP v1 data-only wakeup notifications (`commands_available`) when `AKDL_FCM_SERVICE_ACCOUNT` is configured; the device always fetches and verifies signed commands from the authenticated REST API.
- **Anti-Reset & Anti-Flashing (`EnrollmentProtection`)**: Enforces `DISALLOW_FACTORY_RESET` (which also locks bootloader OEM Unlock), `DISALLOW_DEBUGGING_FEATURES` (post-registration), `DISALLOW_USB_FILE_TRANSFER`, `DISALLOW_MOUNT_PHYSICAL_MEDIA`, `DISALLOW_NETWORK_RESET`, `DISALLOW_SAFE_BOOT`, and `setUninstallBlocked`.

## 4. Known Hardware & OS Realities

- **Hardware Recovery Reset**: If a user powers off the device and performs a hardware key-combination wipe from the bootloader/recovery menu, Android OS is not running and no DPC can block it. Protection against recovery wipe relies on Google Factory Reset Protection (FRP), Zero-Touch Enrollment, or Samsung Knox Guard.
