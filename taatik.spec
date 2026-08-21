# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)

a = Analysis(
    [str(root / "taatik_launcher.py")],
    pathex=[str(root)],
    binaries=[
        (str(path), "bin")
        for path in (root / "vendor" / "bin").glob("*")
        if path.is_file()
    ],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="Taatik", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=True, console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name="Taatik")
