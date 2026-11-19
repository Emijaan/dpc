plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.akdevicelock.dpc"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.akdevicelock.dpc"
        minSdk = 28 // Vivo 1902 test device runs Android 9
        targetSdk = 30 // Android 11 test device; raise after compatibility testing
        versionCode = 1
        versionName = "0.1.0"
    }
    buildTypes {
        release { isMinifyEnabled = false }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures { buildConfig = true }
    kotlinOptions { jvmTarget = "17" }
}
