#!/bin/bash
# One-shot macOS packaging: icon -> PyInstaller .app -> ad-hoc sign -> DMG
cd /Users/yuanyong/gitee/can_parser_ai || exit 1
exec >>/tmp/build_dmg.log 2>&1
echo "===== BUILD START $(date) ====="
set -x

# ---- 1. Generate .icns icon from can-bus.png ----
rm -rf build_icon.iconset
mkdir build_icon.iconset
for s in 16 32 128 256 512; do
  sips -z $s $s can-bus.png --out "build_icon.iconset/icon_${s}x${s}.png" || exit 1
  d=$((s * 2))
  sips -z $d $d can-bus.png --out "build_icon.iconset/icon_${s}x${s}@2x.png" || exit 1
done
iconutil -c icns build_icon.iconset -o can_parser.icns || exit 1
rm -rf build_icon.iconset
echo "--- icon done ---"

# ---- 2. PyInstaller build ----
rm -rf build dist
python3 -m PyInstaller --noconfirm --clean can_parser.spec || exit 1
echo "--- pyinstaller done ---"

# ---- 3. Ad-hoc codesign (best effort) ----
codesign --force --deep --sign - "dist/CAN Bus Parser.app" || echo "WARN: codesign failed"
echo "--- codesign done ---"

# ---- 4. Smoke test (offscreen, must stay alive 8s) ----
python3 - <<'EOF'
import os, subprocess, time, sys
exe = "dist/CAN Bus Parser.app/Contents/MacOS/CAN Bus Parser"
env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
p = subprocess.Popen([exe], env=env)
time.sleep(8)
rc = p.poll()
p.kill()
p.wait()
print("smoke poll rc:", rc, "(None => stayed running => OK)")
if rc is not None:
    sys.exit(1)
EOF
echo "--- smoke test done ---"

# ---- 5. Build DMG ----
STAGE=dist/dmg_stage
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "dist/CAN Bus Parser.app" "$STAGE/" || exit 1
cp "README_使用须知.txt" "$STAGE/" || true
ln -s /Applications "$STAGE/Applications"
rm -f "dist/CAN_Bus_Parser_macOS_x86_64.dmg"
hdiutil create -volname "CAN Bus Parser" -srcfolder "$STAGE" -ov -format UDZO "dist/CAN_Bus_Parser_macOS_x86_64.dmg" || exit 1
rm -rf "$STAGE"
echo "--- dmg done ---"

ls -lh dist/
echo "===== BUILD COMPLETE $(date) ====="
