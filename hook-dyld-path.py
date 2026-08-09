"""PyInstaller runtime hook: expose bundled dylibs (e.g. libPCBUSB for PCAN-USB
live capture) to ctypes.util.find_library via DYLD_FALLBACK_LIBRARY_PATH."""

import os
import sys

_meipass = getattr(sys, "_MEIPASS", None)
if _meipass:
    # Search both the extraction dir and the executable dir (the .app bundle
    # keeps binaries next to the executable in Contents/MacOS).
    _extra = [_meipass, os.path.dirname(os.path.abspath(sys.executable))]
    _seen, _paths = set(), []
    for _p in _extra + os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "").split(os.pathsep):
        if _p and _p not in _seen:
            _seen.add(_p)
            _paths.append(_p)
    os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = os.pathsep.join(_paths)
