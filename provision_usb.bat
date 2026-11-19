@echo off
title AK DeviceLock - 1-Click USB Device Owner Provisioner
echo ========================================================
echo   AK DeviceLock - 1-Click USB Device Owner Provisioner
echo ========================================================
echo.
echo Checking connected Android device...
adb devices
echo.
echo Disabling ADB package verifier for smooth installation...
adb shell settings put global verifier_verify_adb_installs 0
adb shell settings put global package_verifier_enable 0
echo.
echo Installing AK DeviceLock APK...
adb install -r "C:\AKDeviceLock\backend\secrets\akdevicelock.apk"
echo.
echo Setting AK DeviceLock as Device Owner...
adb shell dpm set-device-owner com.akdevicelock.dpc/.deviceadmin.AkDeviceAdminReceiver
echo.
echo Launching AK DeviceLock (auto-registers with server)...
adb shell am start -n com.akdevicelock.dpc/.status.MainActivity
echo.
echo Done! Verify the device is ONLINE at:
echo https://dpc.apinfotechandcybersolution.com/panel/
pause
