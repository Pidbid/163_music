#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

BINARY="dist/163-music"
if [[ ! -x "${BINARY}" ]]; then
  echo "build_appimage.sh requires dist/163-music (run ./build_linux.sh first)" >&2
  exit 1
fi

APP_VERSION="$(python3 -c 'import re; from pathlib import Path; print(re.search(r"__version__ = \"([^\"]+)\"", Path("nm_shell/version.py").read_text()).group(1))')"
APPIMAGETOOL="${APPIMAGETOOL:-$(command -v appimagetool || true)}"
if [[ -z "${APPIMAGETOOL}" || ! -x "${APPIMAGETOOL}" ]]; then
  echo "appimagetool is required; set APPIMAGETOOL or install it" >&2
  exit 1
fi

APPDIR="dist/appimage/163-music.AppDir"
OUTPUT="dist/163-music-${APP_VERSION}-x86_64.AppImage"
rm -rf "${APPDIR}"
rm -f "${OUTPUT}"
mkdir -p "${APPDIR}/usr/bin"

cp "${BINARY}" "${APPDIR}/usr/bin/163-music"
chmod 0755 "${APPDIR}/usr/bin/163-music"
cp assets/icon-512.png "${APPDIR}/163-music.png"

cat > "${APPDIR}/163-music.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=网易云音乐
Comment=非官方网易云音乐网页版桌面封装
Exec=163-music
Icon=163-music
Terminal=false
Categories=AudioVideo;Audio;Player;
StartupWMClass=163-music
EOF

cat > "${APPDIR}/AppRun" <<'EOF'
#!/bin/sh
exec "$APPDIR/usr/bin/163-music" "$@"
EOF
chmod 0755 "${APPDIR}/AppRun"

if command -v desktop-file-validate >/dev/null 2>&1; then
  desktop-file-validate "${APPDIR}/163-music.desktop"
fi

if ! ARCH=x86_64 "${APPIMAGETOOL}" --appimage-extract-and-run "${APPDIR}" "${OUTPUT}" 2>/dev/null; then
  rm -f "${OUTPUT}"
  ARCH=x86_64 "${APPIMAGETOOL}" "${APPDIR}" "${OUTPUT}"
fi

echo "AppImage complete: ${OUTPUT}"
sha256sum "${OUTPUT}"
