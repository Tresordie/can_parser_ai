# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for CAN Bus Parser (macOS .app bundle)."""

block_cipher = None

import os

# Bundle the MacCAN PCBUSB userland driver so PCAN-USB live capture works on
# machines without a separately installed driver. Only added when present on
# the build machine.
_binaries = []
for _cand in ('/usr/local/lib/libPCBUSB.dylib', '/usr/local/lib/libPCBUSB.0.12.dylib'):
    if os.path.exists(_cand):
        _binaries.append((_cand, '.'))
        break

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_binaries,
    datas=[('can-bus.png', '.')],
    hiddenimports=[
        # python-can interfaces are loaded dynamically via importlib
        'can.interfaces.pcan',
        'can.interfaces.kvaser',
        'can.interfaces.socketcan',
        'can.interfaces.vector',
        'can.interfaces.virtual',
        'can.interfaces.slcan',
        'can.interfaces.serial',
        'can.io.asc',
        'can.io.blf',
        'can.io.csv',
        'can.io.trc',
        'can.io.logger',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['hook-dyld-path.py'],
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
    name='CAN Bus Parser',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='CAN Bus Parser',
)

app = BUNDLE(
    coll,
    name='CAN Bus Parser.app',
    icon='can_parser.icns',
    bundle_identifier='com.canbus.parser',
    info_plist={
        'CFBundleName': 'CAN Bus Parser',
        'CFBundleDisplayName': 'CAN Bus Parser',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'NSHighResolutionCapable': True,
        'NSPrincipalClass': 'NSApplication',
    },
)
