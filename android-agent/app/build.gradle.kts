plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Release signing comes from environment variables so no secret is stored in the repo.
val ksPath: String? = System.getenv("AKDL_KEYSTORE")

android {
    namespace = "com.akdevicelock.dpc"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.akdevicelock.dpc"
        minSdk = 28 // Vivo 1902 (Android 9) through Samsung Android 16
        targetSdk = 35
        versionCode = 7
        versionName = "0.7.0"
    }
    signingConfigs {
        if (ksPath != null) {
            create("release") {
                storeFile = file(ksPath)
                storePassword = System.getenv("AKDL_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("AKDL_KEY_ALIAS") ?: "akdl"
                keyPassword = System.getenv("AKDL_KEYSTORE_PASSWORD")
            }
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            if (ksPath != null) signingConfig = signingConfigs.getByName("release")
        }
    }
    buildFeatures { buildConfig = true }
    lint {
        disable += "ExpiredTargetSdkVersion"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}
