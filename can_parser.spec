# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for CAN Bus Parser v0.1 — cross-platform standalone build."""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

is_win = sys.platform == "win32"
is_mac = sys.platform == "darwin"

app_name = "CAN_Bus_Parser"
icon_file = os.path.join(SPECPATH, "can-bus.png")
entry_script = os.path.join(SPECPATH, "main.py")

hiddenimports = [
    "matplotlib.backends.backend_qt5agg",
    "matplotlib.backends.backend_svg",
    "PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets",
    "can.interfaces.pcan",
    "can.interfaces.socketcan",
    "can.interfaces.virtual",
    "cantools.database.can",
    "encodings",
]

datas = []
datas += collect_data_files("matplotlib", subdir="mpl-data")
if os.path.exists(icon_file):
    datas.append((icon_file, "."))

excludes = [
    "tkinter", "_tkinter",
    "IPython", "jupyter", "ipykernel",
    "numpy.tests", "numpy.doc",
    "scipy", "pandas", "cv2",
]

a = Analysis(
    [entry_script],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe_kwargs = {"name": app_name, "console": False}
if is_win:
    exe_kwargs["icon"] = icon_file
elif is_mac:
    exe_kwargs["icon"] = icon_file
    exe_kwargs["bundle_identifier"] = "com.simonyuan.canbusparser"

exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [], **exe_kwargs)

if is_mac:
    app = BUNDLE(
        exe,
        name=f"{app_name}.app",
        icon=icon_file,
        bundle_identifier="com.simonyuan.canbusparser",
        info_plist={
            "NSHighResolutionCapable": "True",
            "CFBundleName": app_name,
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
            "NSHumanReadableCopyright": "MIT",
        },
    )

if is_win or not is_mac:
    coll = COLLECT(
        exe, a.binaries, a.zipfiles, a.datas,
        strip=False, upx=True, upx_exclude=[], name=app_name,
    )
