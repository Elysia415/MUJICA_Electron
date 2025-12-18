# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Calculate absolute paths
SPEC_DIR = os.path.dirname(os.path.abspath(SPECPATH))
print(f"DEBUG: SPEC_DIR = {SPEC_DIR}")

# Try to find source directory
found_source = False
possible_paths = [
    os.path.join(os.path.dirname(SPEC_DIR), 'source'), # ../source
    os.path.join(SPEC_DIR, 'source'), # ./source
    os.path.join(os.path.dirname(os.path.dirname(SPEC_DIR)), 'source'), # ../../source
]

SOURCE_DIR = None
for p in possible_paths:
    if os.path.exists(p) and os.path.exists(os.path.join(p, 'src')):
        SOURCE_DIR = p
        break

if not SOURCE_DIR:
    # Fallback to hardcoded assumption if dynamic search fails, but print error
    print("ERROR: Could not find 'source/src' in expected locations.")
    print(f"Checked: {possible_paths}")
    # Default to first option to let PyInstaller error out normally if needed
    SOURCE_DIR = possible_paths[0]
else:
    print(f"DEBUG: Found SOURCE_DIR = {os.path.abspath(SOURCE_DIR)}")

SRC_DIR = os.path.join(SOURCE_DIR, 'src')
PROJECT_ROOT = os.path.dirname(SOURCE_DIR)
# NOTE: Do NOT bundle .env file - user config should be in %APPDATA%/MUJICA/.env

# Prepare datas list
_datas = [
    (SRC_DIR, 'src'),
]
# Removed: .env file bundling - this would expose dev credentials

a = Analysis(
    ['app.py'],
    pathex=[SOURCE_DIR],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan.on',
        'engineio.async_drivers.aiohttp',
        'tiktoken_ext.openai_public',
        'tiktoken_ext',
        # LanceDB and Arrow dependencies
        'lancedb',
        'pyarrow',
        'pyarrow.parquet',
        'pyarrow.compute',
        'pyarrow.lib',
        'pandas',
        'pandas._libs',
        'pandas._libs.lib',
        'numpy',
        # Additional imports for import_kb
        'zipfile',
        'tempfile',
        'shutil',
        'sqlite3',
    ] + collect_submodules('lancedb') + collect_submodules('pyarrow'),
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
    name='mujica_backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='mujica_backend',
)
