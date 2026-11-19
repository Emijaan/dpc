# Milestone 1 — Existing Project Audit, Baseline & Architecture Plan

Date: 2026-11-20 · Repo HEAD: `9e96821` + uncommitted ownership/isolation work (see §2).

## 1. Backup

| Item | Value |
|---|---|
| Archive | `/Users/macbook/Documents/PERSONAL/dpc-backups/dpc-pre-milestone1-20261120-003456.tar.gz` |
| SHA-256 | `cf276bb3137ac21174789c00e4e90e355a194dd44967ebffa5759efc8faeeccd` |
| Contents | Full working tree incl. uncommitted changes (244 files). Excludes `.venv`, `__pycache__`, `db.sqlite3`, `backend/secrets/`, `*.pem`, build dirs (secrets deliberately not archived). |
| Git | Last commit `9e96821`; ownership/isolation work is **uncommitted** — only the tarball preserves it. |

Server (`3.106.214.246:/opt/akdevicelock`) is not a git checkout; it is `rsync`-deployed. Production DB is **PostgreSQL**; secrets live in `/etc/akdl/akdl.env`, signing keys in `/etc/akdl/keys`. No Redis, no Celery on the server today.

## 2. Current system inventory

### Android (`android-agent/`, ~1,800 LOC Kotlin, package `com.akdevicelock.dpc`, v0.9.0, versionCode 9)
- `minSdk 28`, `targetSdk/compileSdk 35`. **No Room, Retrofit/OkHttp or Firebase client** — uses `HttpURLConnection` (`ApiClient`) and `SharedPreferences`.
- Lock engine (the part to preserve):
  - `LockManager` interface (`lock()/unlock()` → `LockResult`).
  - **`KioskRestrictionManager`** — the production lock: Lock Task Mode + `LockedHomeAlias` as persistent preferred HOME + status bar disabled + dialer whitelisted + `DISALLOW_APPS_CONTROL/UNINSTALL_APPS`; state in device-protected storage (`RestrictionState`) so it survives reboot / Direct Boot (`BootReceiver`).
  - `DevicePolicyLockManager` — `lockNow()` screen lock.
  - `FinancingDeviceLockManager` — Android 14+ `DeviceLockManager`; **stub** (always returns Failure; needs FINANCING role).
  - `EnrollmentProtection` — factory-reset/safe-boot/add-user/USB-transfer/network-reset restrictions, ADB disabled after registration, uninstall block, hides Test DPC.
  - `RemoteUnlockEngine` — unlock + two-phase release (`prepareRelease` → ack → `finalizeRelease`).
- Command pipeline: `CommandPollService` (authenticated polling) → `CommandExecutor` (idempotent replay table, nonce check) → `CommandVerifier` (type allow-list, UUIDs, device binding, skew-tolerant expiry, **ECDSA P-256/SHA-256** over `id|device_id|type|issued|expires|nonce|reason[|key_id]`) → lock engine → `acknowledge`.
- Identity: `DeviceKeyManager` (Android Keystore EC key, public key registered), `SecureStore` (Keystore AES-GCM token storage, 7-day token renewal).
- Provisioning: `ProvisioningActivity`/`Enrollment.kt`, QR admin-extras bundle (`server_url`, `enrollment_key`).
- Tests: `CommandVerifierTest` (5 JVM tests).

### Backend (`backend/`, Django 6 / DRF, PostgreSQL in prod)
Apps: `accounts, roles, devices, commands, notifications, keymanagement, audit`.
Done and tested (29 tests): hierarchy via `AccountProfile` (SUPERUSER/RETAILER/VENDOR), scoped querysets + `can_access_*` centralized in `devices/ownership.py`, ownership fields + immutability guard + Superuser-only transfer with audit, encrypted/masked IMEI and customer PII, single-use short-lived `EnrollmentSession` tokens (QR/BAT are session-scoped), signed commands bound to a device, key rotation/revocation, FCM HTTP v1 wake-up (no-op until configured), simple per-account `entitlement_quota` counter, server-rendered panel (tabs: Devices, Users & Limits, Enrollments, Activity, Security).

### Verified Android version behaviour (from `documentation/COMPATIBILITY_AND_SECURITY.md`, `testing/TEST_REPORT.md`)
| Android | Evidence | Status |
|---|---|---|
| 9 (SDK 28) | vivo 1902, real device | Provisioning, `lockNow`, kiosk, reboot persistence, remote lock/unlock **PASS** |
| 10–11 | none | **Untested** (minSdk allows) |
| 12–15 | none on hardware | **Untested**; Test DPC 9.0.12 transfer path is design-intent only |
| 16 (SDK 36) | Samsung SM-X115 | Device Owner via ADB **PASS only with Auto Blocker OFF + no accounts**; registration & restrictions PASS. Lock/unlock on A16 **not recorded**. Test DPC 9.0.12 crashes on API 36; 9.0.16 disabled `transferOwnership` |
| **8 (SDK 26–27)** | — | **Not supported**: `minSdk 28`. The master prompt asks for 8–16 |

## 3. Regression baseline (what I could and could not run)

| Suite | Result |
|---|---|
| Django `manage.py test` | **29/29 PASS** (19 legacy + 10 ownership/isolation/quota) |
| `manage.py check`, `makemigrations --check` | clean |
| Android `./gradlew testDebugUnitTest` | **Cannot run here**: no JDK, no Android SDK, no `adb`, no `gradle` on this Mac. Last recorded result (TEST_REPORT.md): 5/5 PASS |
| On-device Android 8–16 | Cannot run here; only the two devices above have ever been tested |

Before touching the Android code in Milestone 11 I need a machine/CI with JDK 17 + Android SDK, or you run the tests and send the output.

## 4. Gap analysis vs. master prompt

| Area | Today | Gap |
|---|---|---|
| Three user types | `AccountProfile` + username/password | No Retailer/Vendor profile tables (business name, address, contact, mobile, email, status); no invitation flow |
| Entitlements | `entitlement_quota` / `entitlements_consumed` counters | **No ledger**: no allocations with 365-day expiry, no parent allocation, no retailer→vendor distribution, vendor↔vendor transfer, append-only consumption table, row-locking/constraints, expiry rules |
| Customer/device registration | Customer + enrollment create; device registered by Android | No pre-registration of device brand/model/IMEI/Android version; no "pending device" record; no IMEI cross-check at enrollment; email required |
| Android 9–15 workflow | Single QR page, static instructions | No guided stepper, "Generate AK DeviceLock QR" step, or verified DO-state reporting; Test DPC version unverified |
| Android 16 BAT | `provision_usb.bat` static at repo root | Not session-scoped; no checks/verification as specified |
| Device authentication | Keystore EC key; ECDSA command signing | Registration-record binding of commands; key-lifecycle UI/audit gaps |
| Commands | Lock/unlock/sync/status/release signed + acked; offline queue | Pending/Lock-Pending status model; **no FCM client in the APK** (device only polls) |
| Statuses | Mixed fields | Separate account/allocation/enrollment/device status model needed |
| Audit | `DeviceAuditLog` (mutable via admin, no unauthorized-attempt logging) | Needs append-only, target-typed, retailer/vendor-scoped, 403 attempts logged |
| Auth | Django session + Basic | **No JWT / refresh rotation** |
| Frontend | Django templates | **No React/TS/Tailwind app** |
| Infra | Nginx+Gunicorn+PG+TLS | No Redis/Celery, no automated backups/monitoring, no staging env |

## 5. Decisions needed before building (recommendations)

1. **Signature algorithm — recommend keeping ECDSA P-256, not Ed25519.** Android Keystore supports Ed25519 only on API 33+, but `minSdk` is 28 (and 26 if Android 8 is added). Ed25519 would break Android 9–12. P-256 is already verified on real devices.
2. **Android 8 support** — requires lowering `minSdk` 28→26 and re-verifying Device Owner provisioning (QR provisioning on 8.0 differs) and `setLockTaskFeatures` (API 28+, would need a guarded fallback). The prompt itself says document limits rather than claim universality. Confirm you want 8 attempted.
3. **Frontend** — rebuilding in React/TS/Tailwind replaces the working Django-template panel. Recommend building it as a new `frontend/` SPA against the new `/api/v1/` JWT API, shipping milestone by milestone while the current panel stays live until feature parity.
4. **Celery/Redis** — only needed for FCM fan-out, expiry sweeps and alerts; recommend adding at Milestone 13, not earlier.
5. **Test DPC version** — "version 12" is unverified; repo uses 9.0.12 (works ≤ API 35, crashes on 36). I will verify the available releases/APK before any workflow depends on it.
6. **Existing data** — production already has devices/users. All new models need data migrations that keep existing rows valid (legacy devices stay platform-owned).

## 6. Proposed architecture

```
 React SPA (frontend/)  ──HTTPS/JWT──►  Nginx ─► Gunicorn ─► Django/DRF (/api/v1)
                                                     │  services layer (authorization + business rules)
 Android DPC ──signed cmds / device token──►         ├─ accounts / retailers / vendors
   (existing LockManager untouched)                  ├─ entitlements (ledger: allocation, transfer, consumption)
                                                     ├─ customers / devices / enrollment
                                                     ├─ commands / keymanagement / notifications(FCM)
                                                     └─ audit (append-only)      PostgreSQL (+Redis/Celery later)
```
Rules: one service layer owns every authorization and entitlement mutation (views stay thin); `devices/ownership.py` is evolved, not replaced; entitlement balances are derived from the ledger inside `SELECT … FOR UPDATE` transactions; commercial "entitlements" and cryptographic "keys" stay in separate apps.

## 7. Milestone plan (each: build → test → report; none starts until the previous passes)

| # | Scope | Verification |
|---|---|---|
| 2 | UI/UX design (wireframes/design system for 3 dashboards, forms, stepper) | Review with you |
| 3 | JWT auth (login/refresh-rotation/logout), env config, API skeleton, rate limits | Auth tests |
| 4 | Retailer/Vendor profiles, full create/edit/activate APIs, hierarchy validation | Tests 1–6 of §18 |
| 5 | Entitlement ledger (allocate/distribute/transfer/consume/expire) | Tests 17–27, concurrency test on PostgreSQL |
| 6–7 | Customer + pending-device registration, ownership/isolation on new APIs | Tests 7–16 |
| 8–9 | Android 9–15 stepper + Android 16 session BAT (verified DO state, no false success) | Backend tests + **real-device runs by you** |
| 10–13 | Registration-bound keys, lock integration, release, FCM client + Celery | Android JVM tests (needs JDK/SDK) + device runs |
| 14–16 | React dashboards | UI/component + API tests |
| 17–18 | Append-only audit, notifications, full isolation suite | Tests 28–36 |
| 19–20 | Compatibility matrix on real devices; production deploy, backups, monitoring | Device matrix, deploy checklist |

## 8. Risks / limits stated up front
- Cannot build/run Android here (no JDK/SDK/adb); Android milestones need your toolchain or devices.
- Only Android 9 and 16 have real-device evidence; 8 and 10–15 will be documented as untested until run.
- Android 16 ADB Device Owner works only on a fresh/unconfigured device (no accounts, Auto Blocker off); the BAT must explain this up front and verify state rather than assume.
- IMEI is not obtainable by a normal app on Android 10+; it will be entered at registration and, where possible, cross-checked only via privileged/provisioning paths — otherwise recorded as "operator-declared".
