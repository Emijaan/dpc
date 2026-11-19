# AK DeviceLock Testing Report

## 1. Real Hardware Testing — vivo 1902 (Android 9, SDK 28)
Date: 2026-11-19

| Test | Result | Notes |
|---|---|---|
| App builds (`assembleDebug` & signed `assembleRelease`, minSdk 28) | PASS | Verified signature with `apksigner verify --print-certs`. |
| Device Owner provisioning (`dpm set-device-owner`) | PASS | 0 accounts, 1 user. Confirmed in `dumpsys device_policy`. |
| `lockNow()` via `DevicePolicyLockManager` | PASS | Screen turned off and locked. User unlocked with their own pattern. |
| Reboot behavior (Device Owner persistence) | PASS | Device Owner persisted after reboot (`dumpsys device_policy`). |
| Kiosk restriction (Lock Task Mode, `KioskRestrictionManager`) | PASS | `dumpsys`: `mLockTaskModeState=LOCKED`. Home/Back/Recents disabled (user confirmed). |
| Emergency dialer in kiosk | PASS | Emergency call button opens dialer; returning to AK DeviceLock works. |
| Kiosk reboot persistence (`BootReceiver`) | PASS | After reboot, `BootReceiver` re-launched `MainActivity` into lock task mode. |
| Kiosk release (debug long-press) | PASS | `dumpsys`: `mLockTaskModeState=NONE`, `kiosk_applied=false`. Phone fully usable. |
| Device registration & Keystore token storage | PASS | Vivo 1902 registered against backend (`/api/v1/devices/register/`), status `ENROLLED` & `ONLINE`. |
| Remote LOCK & UNLOCK via Control Panel | PASS | Operator triggered LOCK & UNLOCK from `/panel/`; device verified ECDSA signature, applied/removed kiosk restriction, and acknowledged execution. |

## 2. Automated Backend Security & Protocol Tests (`python manage.py test` — 14/14 PASS)

| Test Case | Result | Verified Behavior |
|---|---|---|
| `test_register_requires_enrollment_key` | PASS | Unauthenticated registration without valid `X-Enrollment-Key` rejected (`403`). |
| `test_duplicate_registration_rejected` | PASS | Re-registering an existing `device_identifier` rejected (`409`). |
| `test_device_endpoints_need_credential` | PASS | Missing or invalid device token rejected (`401`/`403`). |
| `test_device_cannot_use_operator_endpoints` | PASS | Device credential cannot call operator lock/unlock endpoints (`403`). |
| `test_lock_flow_signature_and_ack` | PASS | ECDSA P-256 signature verifies over canonical payload; `restriction_status` updates to `LOCKED` only after device acknowledges `success=True`; duplicate ack is idempotent. |
| `test_duplicate_lock_command_not_created` | PASS | Creating a second pending lock command returns existing command (`duplicate=True`). |
| `test_expired_command_not_delivered` | PASS | Commands past `expires_at` transition to `EXPIRED` and are not delivered. |
| `test_offline_command_waits_then_delivered` | PASS | Commands created while device is offline remain `PENDING` and deliver upon reconnect. |
| `test_other_device_cannot_ack` | PASS | A device cannot acknowledge commands belonging to another device (`404`). |
| `test_release_revokes_device` | PASS | `DEVICE_RELEASE` marks device `RELEASED` and revokes future token authentication (`401`). |
| `test_renew_token_invalidates_old` | PASS | Credential rotation invalidates previous token and activates new token. |
| `test_panel_requires_staff` | PASS | Unauthenticated requests to `/panel/` redirect to login (`302`). |
| `test_audit_trail` | PASS | All registration, creation, delivery, and ack events are recorded in `DeviceAuditLog`. |
| `test_qr_provisioning_payload_and_page` | PASS | `/panel/qr/` generates valid Android Enterprise QR payload with `PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM` and renders inline SVG QR. |
