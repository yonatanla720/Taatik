# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path
import tomllib

root = Path(SPECPATH)
app_version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
vendor_bin = Path(os.environ.get("TAATIK_VENDOR_BIN", root / "vendor" / "bin"))
license_dir_value = os.environ.get("TAATIK_LICENSE_DIR")
license_dir = Path(license_dir_value) if license_dir_value else None
icon_value = os.environ.get("TAATIK_MAC_ICON")
icon_path = Path(icon_value) if icon_value else None
win_icon_value = os.environ.get("TAATIK_WIN_ICON")
win_icon_path = Path(win_icon_value) if win_icon_value else None

datas = [(str(root / "THIRD_PARTY_NOTICES.md"), ".")]
if license_dir and license_dir.is_dir():
    datas.append((str(license_dir), "licenses"))

a = Analysis(
    [str(root / "taatik_launcher.py")],
    pathex=[str(root)],
    binaries=[
        (str(path), "bin")
        for path in vendor_bin.glob("*")
        if path.is_file()
    ],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="Taatik", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=sys.platform == "win32", console=False,
    icon=str(win_icon_path) if win_icon_path and win_icon_path.is_file() else None,
)
coll = COLLECT(
    exe, a.binaries, a.datas, strip=False, upx=sys.platform == "win32", name="Taatik"
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Taatik.app",
        icon=str(icon_path) if icon_path and icon_path.is_file() else None,
        bundle_identifier="app.taatik.desktop",
        version=app_version,
        info_plist={
            "CFBundleDisplayName": "Taatik",
            "CFBundleName": "Taatik",
            "LSApplicationCategoryType": "public.app-category.productivity",
            "LSMinimumSystemVersion": "13.3",
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "Taatik contributors",
        },
    )
