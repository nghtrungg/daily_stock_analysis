# -*- coding: utf-8 -*-
"""Regression checks for desktop installer configuration."""

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DESKTOP_DIR = REPO_ROOT / "apps" / "dsa-desktop"
LOCAL_APP_ID = "com.nghtrungg.daily-stock-analysis-vietnam"
LOCAL_PRODUCT_NAME = "Daily Stock Analysis Vietnam"
LOCAL_WINDOWS_ARTIFACT = "daily-stock-analysis-vietnam-windows-installer-v${version}.${ext}"


def test_windows_nsis_build_allows_custom_install_directory() -> None:
    package_json = json.loads((DESKTOP_DIR / "package.json").read_text(encoding="utf-8"))
    nsis = package_json.get("build", {}).get("nsis", {})

    assert nsis.get("oneClick") is False
    assert nsis.get("allowToChangeInstallationDirectory") is True
    assert nsis.get("allowElevation") is False
    assert nsis.get("include") == "installer.nsh"


def test_installer_blocks_system_protected_directories() -> None:
    installer_script = (DESKTOP_DIR / "installer.nsh").read_text(encoding="utf-8")

    assert "Function .onVerifyInstDir" in installer_script
    assert "$PROGRAMFILES" in installer_script
    assert "$PROGRAMFILES64" in installer_script
    assert "$PROGRAMFILES32" in installer_script
    assert "$WINDIR" in installer_script
    assert "Abort" in installer_script


def test_old_uninstaller_retry_quotes_install_location_parameter() -> None:
    installer_script = (DESKTOP_DIR / "installer.nsh").read_text(encoding="utf-8")

    assert '"_?=$R8"' in installer_script
    assert "Retrying old uninstaller with quoted _? installation directory." in installer_script


def test_local_vietnam_desktop_identity_is_isolated_from_upstream() -> None:
    package_json = json.loads((DESKTOP_DIR / "package.json").read_text(encoding="utf-8"))
    build = package_json.get("build", {})
    windows = build.get("win", {})

    assert build.get("appId") == LOCAL_APP_ID
    assert build.get("productName") == LOCAL_PRODUCT_NAME
    assert windows.get("artifactName") == LOCAL_WINDOWS_ARTIFACT
    assert "publish" not in windows
    assert "electron-updater" not in package_json.get("dependencies", {})


def test_local_vietnam_desktop_disables_upstream_update_network_paths() -> None:
    main_js = (DESKTOP_DIR / "main.js").read_text(encoding="utf-8")

    assert "const DESKTOP_UPDATES_ENABLED = false;" in main_js
    assert "ZhuLinsen" not in main_js
    assert "require('electron-updater')" not in main_js
    assert "if (!DESKTOP_UPDATES_ENABLED)" in main_js


def test_desktop_release_scripts_match_local_vietnam_packaging() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "desktop-release.yml").read_text(
        encoding="utf-8"
    )
    verifier = (REPO_ROOT / "scripts" / "verify-desktop-updater-artifacts.ps1").read_text(
        encoding="utf-8"
    )
    build_script = (REPO_ROOT / "scripts" / "build-desktop.ps1").read_text(
        encoding="utf-8"
    )
    mac_build_script = (REPO_ROOT / "scripts" / "build-desktop-macos.sh").read_text(
        encoding="utf-8"
    )

    assert "daily-stock-analysis-vietnam-windows-installer-$env:RELEASE_TAG.exe" in workflow
    assert "daily-stock-analysis-vietnam-macos-${{ matrix.arch }}-${RELEASE_TAG}.dmg" in workflow
    assert "latest.yml" not in workflow
    assert "daily-stock-analysis-vietnam-windows-installer-v$normalizedReleaseTag.exe" in verifier
    assert "Local Vietnam desktop package must not include an auto-update publisher." in verifier
    assert "electron-updater missing" not in build_script
    assert "electron-updater missing" not in mac_build_script
    assert 'Get-Process -Name "Daily Stock Analysis Vietnam"' in build_script
