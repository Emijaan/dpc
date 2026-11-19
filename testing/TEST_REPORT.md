# AK DeviceLock Testing Report

## Device: vivo 1902 (Android 9, SDK 28)
Date: 2026-11-19

| Test | Result | Notes |
|---|---|---|
| App builds (assembleDebug, minSdk 28) | PASS | |
| Device Owner provisioning (`dpm set-device-owner`) | PASS | 0 accounts, 1 user. Confirmed in `dumpsys device_policy`. |
| `lockNow()` via DevicePolicyLockManager | PASS | Screen turned off and locked. User unlocked with their own pattern. |
| Reboot behavior | PASS (ownership) | Device Owner persisted after reboot (dumpsys). Lock persistence after reboot not applicable to lockNow(). |
| Kiosk restriction (Lock Task Mode, KioskRestrictionManager) | PASS | dumpsys: mLockTaskModeState=LOCKED. Home/Back/Recents disabled (user confirmed). |
| Emergency dialer in kiosk | PASS | Emergency call button opens dialer; returning to AK DeviceLock works. No real call placed. |
| Kiosk reboot persistence | PASS (with delay) | After adb reboot, home screen showed briefly, then restricted screen appeared after a few seconds. Brief window of access exists; improve later (e.g. set app as persistent preferred home). Power menu is disabled while restricted (reboot via adb). |
| Kiosk release (debug long-press) | PASS | dumpsys: mLockTaskModeState=NONE, kiosk_applied=false. Phone fully usable. |
| Remote lock/unlock, backend, offline, replay, expiry | NOT IMPLEMENTED | |
| Release / recovery | NOT TESTED | |

## Conclusions
- `lockNow()` is a one-time screen lock. The user's own pattern unlocks it, so it is not a persistent lock.
- Remote unlock cannot be done with `lockNow()`. A persistent restriction needs Lock Task Mode (next).
- Whether the app displayed "Device Owner: YES" was not reported.

