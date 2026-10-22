# Builds a debug APK: web export -> Capacitor sync -> Gradle.
#   powershell -ExecutionPolicy Bypass -File scripts\build-apk.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\build-apk.ps1 -AllowHttp   # for a plain-http LAN gateway
param([switch]$AllowHttp)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

# Capacitor 8 needs JDK 21. Android Studio ships one; prefer it over an older JAVA_HOME.
$jbr = "C:\Program Files\Android\Android Studio\jbr"
if (Test-Path "$jbr\bin\java.exe") { $env:JAVA_HOME = $jbr }
Write-Host "Using JAVA_HOME=$env:JAVA_HOME"

if (-not (Test-Path ".env.local")) {
    Write-Warning ".env.local not found: the app will have no default server (it can be entered on the login screen)."
}
if ($AllowHttp) { $env:CAP_ALLOW_HTTP = "1" } else { Remove-Item Env:CAP_ALLOW_HTTP -ErrorAction SilentlyContinue }

npm run build
if ($LASTEXITCODE -ne 0) { throw "Web build failed" }
npx cap sync android
if ($LASTEXITCODE -ne 0) { throw "Capacitor sync failed" }

Push-Location android
.\gradlew.bat assembleDebug
$code = $LASTEXITCODE
Pop-Location
if ($code -ne 0) { throw "Gradle build failed" }

$apk = Resolve-Path "android\app\build\outputs\apk\debug\app-debug.apk"
Write-Host ""
Write-Host "APK: $apk" -ForegroundColor Green
Write-Host "Install on a USB-connected phone:  adb install -r `"$apk`""
