<#
  Builds the Eidovia Android app: ONE APK (the Expo app) with the Unity AR game inside it.
  It uses the JDK that ships with the Unity Editor and an Android SDK in %LOCALAPPDATA%\Android\Sdk
  (or $env:ANDROID_HOME). Missing SDK parts are linked from Unity's SDK; Gradle downloads the rest
  (the NDK for React Native), so Android Studio is not needed.

    1. Unity (AR Game project):  Eidovia > Export for Mobile App
    2. Unity: Eidovia > Build Mobile App (APK)     -- or, in apps/mobile:
       powershell -ExecutionPolicy Bypass -File scripts\build-android.ps1 [-Variant debug] [-Install]

  Output: apps/mobile/dist/Eidovia-<variant>.apk   Log: apps/mobile/dist/build-android.log
#>
param(
  [ValidateSet('release', 'debug')][string]$Variant = 'release',
  [switch]$Install
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
  # prebuild rewrites the "android"/"ios" scripts in package.json; keep the file exactly as it is
  $pkg = Join-Path $app 'package.json'
  $pkgBytes = [IO.File]::ReadAllBytes($pkg)
  try { Run 'npx.cmd' @('expo', 'prebuild', '--platform', 'android', '--clean', '--no-install') }
  finally { [IO.File]::WriteAllBytes($pkg, $pkgBytes) }

  Set-Location (Join-Path $app 'android')
  $task = if ($Variant -eq 'release') { 'assembleRelease' } else { 'assembleDebug' }
  Run '.\gradlew.bat' @($task, '--console=plain')

  $apk = Join-Path $app "android\app\build\outputs\apk\$Variant\app-$Variant.apk"
  $out = Join-Path $dist "Eidovia-$Variant.apk"
  Copy-Item $apk $out -Force
  Say ("BUILD OK: {0} ({1:N0} MB)" -f $out, ((Get-Item $out).Length / 1MB))
  if ($Install) { Run 'adb.exe' @('install', '-r', $out) }
}
catch {
  Say "BUILD FAILED: $($_.Exception.Message)"
  exit 1
}
finally {
  $writer.Dispose()
}
