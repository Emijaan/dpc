# Provisioning AK DeviceLock as Device Owner (Samsung Android 11)

APK: `C:\AKDeviceLock\android-agent\app\build\outputs\apk\debug\app-debug.apk`

## Test method (ADB, development only)
1. Factory-reset the phone. During setup, skip Wi-Fi/Google account sign-in (any account on the device makes `dpm set-device-owner` fail).
2. Enable Developer options and USB debugging. Connect the phone by USB.
3. PowerShell:
```
adb devices
adb install C:\AKDeviceLock\android-agent\app\build\outputs\apk\debug\app-debug.apk
adb shell dpm set-device-owner com.akdevicelock.dpc/.deviceadmin.AkDeviceAdminReceiver
adb shell dumpsys device_policy
```
(`dpm list-owners` only exists on Android 10+. Test device: Vivo 1902, Android 9, which works with the same steps.)
4. Open the app. It should show "Device Owner: YES". Tap "Test lockNow()".

Samsung may refuse with "Not allowed to set the device owner..." if a Samsung/Google account exists. Remove accounts or reset again.

## Capabilities and limits (Android 11)
- `lockNow()` locks the screen once. The user can unlock it with their own credentials. It is not a persistent lock.
- Persistent restriction needs Lock Task Mode (planned) or DeviceLockManager (Android 14+, compatible devices only, to be investigated).

## Release
To remove the owner during testing: `adb shell dpm remove-active-admin com.akdevicelock.dpc/.deviceadmin.AkDeviceAdminReceiver`. This only works for test-only DPCs. Otherwise factory-reset.
Production release will be implemented via `clearDeviceOwnerApp()` on an authenticated DEVICE_RELEASE command.

