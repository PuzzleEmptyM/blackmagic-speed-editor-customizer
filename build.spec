# build.spec — PyInstaller build configuration for Speed Editor Customizer
# Cross-platform: works on Windows (produces .exe) and macOS (produces .app)
# Run with:  python -m PyInstaller build.spec --clean

import sys
import os
import glob as _glob
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
IS_WIN = sys.platform == 'win32'
IS_MAC = sys.platform == 'darwin'

# ---------------------------------------------------------------------------
# hidapi native library — must land at bundle root so ctypes can find it
# collect_all puts it in hid/ subdirectory which ctypes doesn't search
# ---------------------------------------------------------------------------

try:
    import hid as _hid_pkg
    _hid_dir = os.path.dirname(_hid_pkg.__file__)
    _hid_native = (
        _glob.glob(os.path.join(_hid_dir, 'hidapi*.dll')) +
        _glob.glob(os.path.join(_hid_dir, 'libhidapi*.dll')) +
        _glob.glob(os.path.join(_hid_dir, '*.dylib')) +
        _glob.glob(os.path.join(_hid_dir, '*.so*'))
    )
    hid_root_bins = [(lib, '.') for lib in _hid_native]
except Exception:
    hid_root_bins = []

# ---------------------------------------------------------------------------
# Platform-specific package collection
# ---------------------------------------------------------------------------

hid_d, hid_b, hid_h = collect_all('hid')
sbc_d, sbc_b, sbc_h = collect_all('screen_brightness_control')

if IS_WIN:
    comtypes_d, comtypes_b, comtypes_h = collect_all('comtypes')
    pycaw_d,    pycaw_b,    pycaw_h    = collect_all('pycaw')
    plat_binaries = comtypes_b + pycaw_b
    plat_datas    = comtypes_d + pycaw_d
    plat_hidden   = (
        comtypes_h + pycaw_h +
        collect_submodules('pynput') +
        [
            'win32api', 'win32con', 'win32gui', 'win32process',
            'win32com', 'win32com.client',
            'pythoncom', 'pywintypes',
            'pynput.keyboard._win32',
            'pynput.mouse._win32',
            'screen_brightness_control.windows',
            'obsws_python',
        ]
    )
else:  # macOS
    plat_binaries = []
    plat_datas    = []
    plat_hidden   = (
        collect_submodules('pynput') +
        [
            'pynput.keyboard._darwin',
            'pynput.mouse._darwin',
            'screen_brightness_control.macos',
            'obsws_python',
        ]
    )

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=hid_b + hid_root_bins + sbc_b + plat_binaries,
    datas=hid_d + sbc_d + plat_datas,
    hiddenimports=hid_h + sbc_h + plat_hidden,
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
    name='SpeedEditorCustomizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=IS_WIN,        # UPX disabled on macOS — breaks Gatekeeper
    console=False,     # no terminal window on either platform
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.ico',  # Windows — uncomment and supply icon.ico
    # icon='icon.icns', # macOS  — uncomment and supply icon.icns
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=IS_WIN,
    upx_exclude=[],
    name='SpeedEditorCustomizer',
)

# macOS: wrap the collected bundle into a proper .app
if IS_MAC:
    app = BUNDLE(
        coll,
        name='SpeedEditorCustomizer.app',
        bundle_identifier='com.speededitorcustomizer',
        info_plist={
            'NSHighResolutionCapable': True,
            'NSAppleEventsUsageDescription':
                'Required for window switching and volume control.',
            'NSMicrophoneUsageDescription': 'Not used.',
        },
    )
