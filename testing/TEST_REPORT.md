# AK DeviceLock Testing Report

## 1. Real Hardware Testing

### Device A: vivo 1902 (Android 9, SDK 28)
Date: 2026-11-19

| Test | Result | Notes |
|---|---|---|
| App builds (`assembleDebug` & signed `assembleRelease`, minSdk 28) | PASS | Verified signature with `apksigner verify --print-certs`. |
| Device Owner provisioning (`dpm set-device-owner` & 2-step transfer) | PASS | Confirmed in `dumpsys device_policy`. |
| `lockNow()` via `DevicePolicyLockManager` | PASS | Screen turned off and locked. User unlocked with their own pattern. |
| Kiosk restriction (Lock Task Mode, `KioskRestrictionManager`) | PASS | `dumpsys`: `mLockTaskModeState=LOCKED`. Home/Back/Recents disabled. |
| Emergency dialer in kiosk | PASS | Emergency call button opens dialer. |
| Reboot persistence (`BootReceiver`) | PASS | Device Owner & kiosk restriction persisted across reboot. |
| Remote LOCK & UNLOCK via Control Panel | PASS | Operator triggered LOCK & UNLOCK from `/panel/`; device verified ECDSA signature and acknowledged. |

### Device B: Samsung SM-X115 (Android 16, SDK 36)
Date: 2026-11-19

| Test | Result | Notes |
|---|---|---|
| Device Owner provisioning (`v0.7.0`, `targetSdk 35`) | PASS | `dpm list-owners`: `com.akdevicelock.dpc/.deviceadmin.AkDeviceAdminReceiver,DeviceOwner,Affiliated` (with Auto Blocker OFF). |
| Device registration & telemetry | PASS | Production PostgreSQL DB recorded `samsung SM-X115 \| Android 16 \| SDK 36 \| v0.7.0 \| ENROLLED`. |
| Anti-reset & anti-flashing policies (`EnrollmentProtection`) | PASS | `DevicePolicyManager` log confirmed `no_factory_reset`, `no_safe_boot`, `no_add_user`, `no_remove_user`, `no_physical_media`, `no_usb_file_transfer`, `no_network_reset = true`. |

## 2. Automated Unit & Backend Tests

- **Android JVM Unit Tests (`./gradlew testDebugUnitTest`)**: 5/5 PASS (`CommandVerifierTest`: valid signature, expired command, wrong device, unauthorized command type, tampered signature).
- **Django Backend Tests (`python manage.py test`)**: 16/16 PASS (registration key enforcement, duplicate registration rejection, token auth, role separation, ECDSA signature & ack flow, duplicate command prevention, expiry, offline queue & reconnect delivery, cross-device isolation, release revocation, token renewal, panel staff auth, audit trail, QR payload & SVG, `/api/v1/docs/`, FCM no-op guard).
