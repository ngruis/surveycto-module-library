from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

project_root = Path(SPECPATH).parent

streamlit_data, streamlit_binaries, streamlit_hidden = collect_all("streamlit")
keyring_data, keyring_binaries, keyring_hidden = collect_all("keyring")

datas = [
    (str(project_root / "app" / "streamlit_app.py"), "app"),
    (str(project_root / "config"), "config"),
    *streamlit_data,
    *keyring_data,
]
binaries = [*streamlit_binaries, *keyring_binaries]
hiddenimports = [
    *streamlit_hidden,
    *keyring_hidden,
    *collect_submodules("surveycto_module_library"),
    *collect_submodules("pysurveycto"),
]

analysis = Analysis(
    [str(project_root / "src" / "surveycto_module_library" / "desktop.py")],
    pathex=[str(project_root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "ruff"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="SurveyCTO Module Library",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    name="SurveyCTO Module Library",
)

if sys.platform == "darwin":
    application = BUNDLE(
        collection,
        name="SurveyCTO Module Library.app",
        bundle_identifier="org.povertyaction.surveycto-module-library",
        info_plist={
            "CFBundleDisplayName": "SurveyCTO Module Library",
            "NSHighResolutionCapable": True,
        },
    )
