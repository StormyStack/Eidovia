<#
  Builds the Eidovia Android app: ONE APK (the Expo app) with the Unity AR game inside it.
  It uses the JDK that ships with the Unity Editor and an Android SDK in %LOCALAPPDATA%\Android\Sdk
  (or $env:ANDROID_HOME). Missing SDK parts are linked from Unity's SDK; Gradle downloads the rest
  (the NDK for React Native), so Android Studio is not needed.

    1. Unity (AR Game project):  Eidovia > Export for Mobile App
    2. Unity: Eidovia > Build Mobile App (APK)     -- or, in apps/mobile:
       powershell -ExecutionPolicy Bypass -File scripts\build-android.ps1 [-Variant debug] [-Install] [-Bundle]

  Output: apps/mobile/dist/Eidovia-<variant>.apk   Log: apps/mobile/dist/build-android.log
  -Bundle also builds dist/Eidovia-release.aab (for Google Play).
  -Clean  regenerates android/ from scratch. Normally it is regenerated only when app.json, package.json,
          the Unity plugin or the Unity export changed; otherwise Gradle reuses its caches (much faster).

  Release builds are signed with YOUR key when apps/mobile/credentials/keystore.properties exists
  (storeFile, storePassword, keyAlias, keyPassword; git-ignored). Keep a backup of that folder:
  without the same key, installed apps cannot be updated. Without it, Android's debug key is used.
#>
param(
  [ValidateSet('release', 'debug')][string]$Variant = 'release',
  [switch]$Install,
  [switch]$Bundle,
  [switch]$Clean
)
$ErrorActionPreference = 'Stop'
$app = Split-Path -Parent $PSScriptRoot
$export = Join-Path $app 'unity\builds\android'
$dist = Join-Path $app 'dist'
New-Item -ItemType Directory -Force $dist | Out-Null
$log = Join-Path $dist 'build-android.log'
$writer = [IO.StreamWriter]::new($log, $false, [Text.UTF8Encoding]::new($false))
$writer.AutoFlush = $true

function Say([string]$line) { Write-Host $line; $writer.WriteLine($line) }

function Run([string]$exe, [string[]]$arguments) {
  Say ">> $exe $($arguments -join ' ')"
  $ErrorActionPreference = 'Continue'          # native tools write progress to stderr
  & $exe @arguments 2>&1 | ForEach-Object { Say "$_" }
  $code = $LASTEXITCODE
  $ErrorActionPreference = 'Stop'
  if ($code -ne 0) { throw "$exe failed with exit code $code" }
}

try {
  if (-not (Test-Path (Join-Path $export 'unityLibrary'))) {
    throw "Unity export not found at $export. In Unity run: Eidovia > Export for Mobile App"
  }

  # Unity's toolchain: the export records where the Editor keeps its JDK and Android SDK
  $props = @{}
  Get-Content (Join-Path $export 'gradle.properties') | ForEach-Object {
    if ($_ -match '^\s*([^#=]+?)\s*=\s*(.*)$') { $props[$matches[1]] = $matches[2] }
  }
  $env:JAVA_HOME = $props['unity.jdkPath'] -replace '/', '\'
  $unitySdk = $props['unity.androidSdkPath'] -replace '/', '\'

  # Unity's SDK is read-only and its NDK is trimmed, so React Native builds against a normal, writable SDK.
  $sdk = $env:ANDROID_HOME
  if (-not $sdk -or $sdk -like '*\Unity\*') { $sdk = Join-Path $env:LOCALAPPDATA 'Android\Sdk' }
  New-Item -ItemType Directory -Force (Join-Path $sdk 'licenses') | Out-Null
  $license = Join-Path $sdk 'licenses\android-sdk-license'
  if (-not (Test-Path $license)) {
    # Android SDK license, accepted by the user for this build
    Set-Content -Path $license -Encoding ascii -Value @('', '8933bad161af4178b1185d1a37fbf41ea5269c55',
      'd56f5187479451eabf01fb78af6dfcb131a6481e', '24333f8a63b6825ea9c5514f83c2829b004d1fee')
  }
  foreach ($part in @("platforms\android-$($props['unity.compileSdkVersion'])", "build-tools\$($props['unity.buildToolsVersion'])",
                      'cmake\3.22.1', 'platform-tools')) {
    $target = Join-Path $unitySdk $part
    $link = Join-Path $sdk $part
    if ((Test-Path $target) -and -not (Test-Path $link)) {
      New-Item -ItemType Directory -Force (Split-Path $link) | Out-Null
      New-Item -ItemType Junction -Path $link -Target $target | Out-Null   # reuse Unity's copy, no download
      Say "linked $part from Unity's SDK"
    }
  }
  $env:ANDROID_HOME = $sdk
  $env:ANDROID_SDK_ROOT = $sdk
  $node = (Get-Command node.exe -ErrorAction SilentlyContinue).Source
  if (-not $node) { $node = Join-Path $env:ProgramFiles 'nodejs\node.exe' }
  if (-not (Test-Path $node)) { throw 'Node.js not found' }
  $env:PATH = "$env:JAVA_HOME\bin;$env:ANDROID_HOME\platform-tools;$(Split-Path $node);$env:PATH"
  $env:EXPO_NO_GIT_STATUS = '1'               # prebuild --clean without the interactive git prompt
  $env:CI = '1'
  Say "JDK:  $env:JAVA_HOME"
  Say "SDK:  $env:ANDROID_HOME"
  Say "Node: $node"

  Set-Location $app
  # android/ only has to be regenerated when what it is made from changed; then Gradle keeps its caches
  $inputs = @('app.json', 'package.json', 'package-lock.json', 'modules\eidovia-unity\app.plugin.js',
              'modules\eidovia-unity\plugin\withEidoviaUnity.js', 'unity\builds\android\EIDOVIA_EXPORT.txt') |
            ForEach-Object { Join-Path $app $_ } | Where-Object { Test-Path $_ }
  $hash = ($inputs | ForEach-Object { (Get-FileHash $_ -Algorithm SHA256).Hash }) -join ''
  $stamp = Join-Path $app 'android\.eidovia-prebuild'
  $fresh = (Test-Path (Join-Path $app 'android\gradlew.bat')) -and (Test-Path $stamp) -and ((Get-Content $stamp -Raw).Trim() -eq $hash)
  if ($Clean -or -not $fresh) {
    # prebuild rewrites the "android"/"ios" scripts in package.json; keep the file exactly as it is
    $pkg = Join-Path $app 'package.json'
    $pkgBytes = [IO.File]::ReadAllBytes($pkg)
    try { Run 'npx.cmd' @('expo', 'prebuild', '--platform', 'android', '--clean', '--no-install') }
    finally { [IO.File]::WriteAllBytes($pkg, $pkgBytes) }
    Set-Content -Path $stamp -Value $hash -Encoding ascii
  } else {
    Say 'android/ is up to date (no prebuild): reusing the Gradle caches'
  }

  # release signing with our own key (prebuild --clean regenerates android/, so it is passed to Gradle here)
  $signing = @()
  $keyProps = Join-Path $app 'credentials\keystore.properties'
  if ($Variant -eq 'release' -and (Test-Path $keyProps)) {
    $k = @{}
    Get-Content $keyProps | ForEach-Object { if ($_ -match '^\s*([^#=]+?)\s*=\s*(.*)$') { $k[$matches[1]] = $matches[2] } }
    $store = Join-Path (Split-Path $keyProps) $k['storeFile']
    if (-not (Test-Path $store)) { throw "Keystore not found: $store" }
    $signing = @("-Pandroid.injected.signing.store.file=$store", "-Pandroid.injected.signing.store.password=$($k['storePassword'])",
                 "-Pandroid.injected.signing.key.alias=$($k['keyAlias'])", "-Pandroid.injected.signing.key.password=$($k['keyPassword'])")
    Say "Signing with the Eidovia release key ($store)"
  } elseif ($Variant -eq 'release') {
    Say 'WARNING: no credentials\keystore.properties - signing with the Android debug key (Play Protect may block the app)'
  }

  Set-Location (Join-Path $app 'android')
  # always re-bundle the JavaScript (Gradle does not notice a changed .env such as the server URL)
  $bundleTask = if ($Variant -eq 'release') { ':app:createBundleReleaseJsAndAssets' } else { ':app:createBundleDebugJsAndAssets' }
  $tasks = @($bundleTask, '--rerun', $(if ($Variant -eq 'release') { 'assembleRelease' } else { 'assembleDebug' }))
  if ($Bundle -and $Variant -eq 'release') { $tasks += 'bundleRelease' }
  $writer.WriteLine(">> .\gradlew.bat $($tasks -join ' ') --console=plain (signing details hidden)")
  $ErrorActionPreference = 'Continue'
  & '.\gradlew.bat' @($tasks + $signing + @('--console=plain')) 2>&1 | ForEach-Object { Say "$_" }
  $code = $LASTEXITCODE
  $ErrorActionPreference = 'Stop'
  if ($code -ne 0) { throw "gradlew failed with exit code $code" }

  $apk = Join-Path $app "android\app\build\outputs\apk\$Variant\app-$Variant.apk"
  $out = Join-Path $dist "Eidovia-$Variant.apk"
  Copy-Item $apk $out -Force
  Say ("BUILD OK: {0} ({1:N0} MB)" -f $out, ((Get-Item $out).Length / 1MB))
  if ($Bundle -and $Variant -eq 'release') {
    $aab = Join-Path $dist 'Eidovia-release.aab'
    Copy-Item (Join-Path $app 'android\app\build\outputs\bundle\release\app-release.aab') $aab -Force
    Say "Google Play bundle: $aab"
  }
  if ($Install) { Run 'adb.exe' @('install', '-r', $out) }
}
catch {
  Say "BUILD FAILED: $($_.Exception.Message)"
  exit 1
}
finally {
  $writer.Dispose()
}
