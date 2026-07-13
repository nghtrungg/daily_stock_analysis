param(
  [string]$DistDir = '',
  [string]$ReleaseTag = '',
  [string]$ReleaseAssetsDir = ''
)

$ErrorActionPreference = 'Stop'

function Resolve-ReleaseTag {
  param([string]$Tag)

  if (-not $Tag) {
    return '';
  }
  return $Tag.Trim();
}

function Normalize-SemverText {
  param([string]$VersionText)

  return ($VersionText -replace '^v', '').Trim();
}

if (-not $DistDir) {
  $DistDir = Join-Path $PSScriptRoot '..\apps\dsa-desktop\dist'
}

$resolvedDistDir = Resolve-Path $DistDir -ErrorAction SilentlyContinue
$distDirPath = ''
if ($resolvedDistDir) {
  $distDirPath = $resolvedDistDir.Path
}
if (-not $distDirPath) {
  Write-Host "[check] dist directory not found: $DistDir"
  Write-Host "[check] if build is not executed on this host, skip validation."
  exit 0
}

$packageJsonPath = Join-Path $PSScriptRoot '..\apps\dsa-desktop\package.json'
if (-not (Test-Path $packageJsonPath)) {
  throw "Package manifest missing: $packageJsonPath"
}

$packageMeta = Get-Content -Path $packageJsonPath -Raw | ConvertFrom-Json
$normalizedPackageVersion = Normalize-SemverText -VersionText $packageMeta.version
if (-not $normalizedPackageVersion) {
  throw "Cannot resolve package version from $packageJsonPath"
}

$normalizedReleaseTag = Normalize-SemverText -VersionText (Resolve-ReleaseTag -Tag $ReleaseTag)
if (-not $normalizedReleaseTag) {
  $normalizedReleaseTag = $normalizedPackageVersion
}

$expectedAppId = 'com.nghtrungg.daily-stock-analysis-vietnam'
$expectedProductName = 'Daily Stock Analysis Vietnam'
if ($packageMeta.build.appId -ne $expectedAppId) {
  throw "Unexpected desktop appId: $($packageMeta.build.appId)"
}
if ($packageMeta.build.productName -ne $expectedProductName) {
  throw "Unexpected desktop productName: $($packageMeta.build.productName)"
}
if ($packageMeta.build.win.PSObject.Properties.Name -contains 'publish') {
  throw 'Local Vietnam desktop package must not include an auto-update publisher.'
}
if ($packageMeta.dependencies -and $packageMeta.dependencies.PSObject.Properties.Name -contains 'electron-updater') {
  throw 'Local Vietnam desktop package must not depend on electron-updater.'
}

$expectedInstallerFileName = "daily-stock-analysis-vietnam-windows-installer-v$normalizedReleaseTag.exe"

$setupFiles = Get-ChildItem -Path $distDirPath -Filter $expectedInstallerFileName -File -ErrorAction SilentlyContinue
if (-not $setupFiles) {
  throw "No expected NSIS installer found in dist: $expectedInstallerFileName"
}

$updateMetadata = Get-ChildItem -Path $distDirPath -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -like 'latest*.yml' }
if ($updateMetadata) {
  $metadataNames = ($updateMetadata | ForEach-Object { $_.Name }) -join ', '
  throw "Unexpected auto-update metadata found in local desktop dist: $metadataNames"
}

$installerFiles = @()
$releaseAssetsDirPath = ''
$releaseAssetsDirWasExplicit = -not [string]::IsNullOrWhiteSpace($ReleaseAssetsDir)

if ($releaseAssetsDirWasExplicit) {
  $resolvedReleaseAssetsDir = Resolve-Path $ReleaseAssetsDir -ErrorAction SilentlyContinue
  if ($resolvedReleaseAssetsDir) {
    $releaseAssetsDirPath = $resolvedReleaseAssetsDir.Path
  }
  if (-not $releaseAssetsDirPath) {
    throw "Release assets directory not found: $ReleaseAssetsDir"
  }
} elseif ((Split-Path -Path $distDirPath -Leaf) -eq 'release-assets') {
  $releaseAssetsDirPath = $distDirPath
} else {
  $defaultReleaseAssetsDir = Join-Path $distDirPath 'release-assets'
  $resolvedReleaseAssetsDir = Resolve-Path $defaultReleaseAssetsDir -ErrorAction SilentlyContinue
  if ($resolvedReleaseAssetsDir) {
    $releaseAssetsDirPath = $resolvedReleaseAssetsDir.Path
  }
}

if ($releaseAssetsDirPath) {
  $installerFiles = Get-ChildItem -Path $releaseAssetsDirPath -Filter $expectedInstallerFileName -File -ErrorAction SilentlyContinue
  if (-not $installerFiles) {
    throw "No expected Windows installer found in release assets: $expectedInstallerFileName"
  }
} else {
  Write-Host "[check] release attachment alias check skipped: run after release assets are prepared or pass -ReleaseAssetsDir."
}

Write-Host "[check] dist: $distDirPath"
Write-Host "[check] expected release version: $normalizedReleaseTag"
Write-Host "[check] NSIS installers:"
$setupFiles | ForEach-Object { Write-Host "[found] $($_.Name)" }
if ($installerFiles) {
  Write-Host "[check] release assets: $releaseAssetsDirPath"
  Write-Host "[check] installer aliases:"
  $installerFiles | ForEach-Object { Write-Host "[found] $($_.Name)" }
}
$versionInTag = Normalize-SemverText -VersionText $ReleaseTag
if ($versionInTag -and $versionInTag -ne $normalizedReleaseTag) {
  Write-Host "[warn] input release tag ($versionInTag) differs from package version ($normalizedReleaseTag)."
}

Write-Host '[check] local Vietnam desktop artifact verification passed.'
exit 0
