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

## 3. Multi-Tenant Platform & Isolation Verification (2026-11-20)

- **Django Backend Suite (`backend/.venv/bin/python manage.py test`)**: **48/48 PASS**:
  - `accounts/tests.py` (12 tests): JWT login, rotating refresh tokens & blacklisting, logout, deactivated user refresh rejection, rate-limited login, audited auth events without secrets, health check.
  - `accounts/tests_hierarchy.py` (1 test, scenarios 1–6): 3-level Superuser/Retailer/Vendor creation, edit, activate/deactivate, cross-retailer & cross-vendor isolation, unauthorized attempt audit logging.
  - `entitlements/tests.py` (3 tests, scenarios 17–27): 365-day allocation, Retailer-to-Vendor distribution, same-Retailer Vendor-to-Vendor transfer, cross-Retailer block, consumed transfer block, concurrent registration race protection, QR/failed-enrollment non-consumption, append-only `EntitlementConsumption`, release non-restoration, expired allocation rejection.
  - `devices/tests_isolation.py` (10 tests): strict tenant ownership boundaries, immutability, QR/BAT secret isolation, Superuser-only audited transfer, panel quota/limit controls.
  - `devices/tests_workflows.py` (3 tests, scenarios 28–36): guided registration (Luhn IMEI + Android 9+ validation), Android 9–15 Test DPC -> AK QR stepper, Android 16 `.bat` safety checks, pending states (`LOCK_PENDING` on offline devices), replay/expiry rejection, append-only `DeviceAuditLog`, background Celery task functions.
  - `devices/tests.py` (19 tests): core registration, ECDSA signing, command ack, token renewal, RBAC, and key rotation/revocation.
- **React + TypeScript + Tailwind SPA (`frontend/`)**: `npm run typecheck` (`tsc --noEmit`) and `npm run build` (`vite build`) passed cleanly (1,604 modules, `0.47 kB` HTML + `15.35 kB` CSS + `328.00 kB` JS).
- **Production Deployment (`3.106.214.246`)**: PostgreSQL migrations applied, `nginx -t` passed, `akdl.service` and `nginx` active, HTTPS `/app/` (`200`) and `/api/v1/health/` (`{"status":"ok"}`) verified.
- **Not run in this environment**: Android Gradle build/unit tests (`./gradlew testDebugUnitTest` — no JDK/Android SDK on host) and live on-device testing of the updated `MainActivity.kt` intent extras and Android 10–15/16 lock/unlock.
