# romtool.spec – PyInstaller build specification for ROMTool
#
# Build command (from the romtool/ directory):
#
#   pyinstaller romtool.spec --noconfirm
#
# Or manually:
#
#   pyinstaller \
#       --noconfirm \
#       --onefile \
#       --windowed \
#       --name ROMTool \
#       --icon assets/icon.ico \
#       --add-data "bin;bin" \
#       main.py
#
# The spec file gives us finer control (e.g. UPX compression on binaries).

import sys
import os
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        # Bundle the entire bin/ directory.
        # Format on Windows: ("source_path", "dest_folder_in_bundle")
        ("bin", "bin"),
    ],
    hiddenimports=[
        # PySide6 plugins that PyInstaller sometimes misses
        "PySide6.QtXml",
        # HTTP / parsing libraries
        "httpx",
        "bs4",
        "httpcore",
        "certifi",
        "charset_normalizer",
        # Optional extraction libraries (include if installed)
        "py7zr",
        "rarfile",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ROMTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,      # Hide the console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Uncomment and set path to embed an application icon:
    # icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ROMTool",
)
