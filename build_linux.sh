#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "build_linux.sh must run on Linux" >&2
  exit 1
fi

for command_name in uv dpkg-deb desktop-file-validate; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "missing build command: ${command_name}" >&2
    exit 1
  fi
done

if [[ "$(dpkg --print-architecture)" != "amd64" ]]; then
  echo "only amd64 DEB builds are supported by this script" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

DEB_ONLY=0
if [[ "${1:-}" == "--deb-only" ]]; then
  DEB_ONLY=1
fi

APP_VERSION="$(uv run python -c 'from nm_shell.version import __version__; print(__version__)')"
DEB_NAME="163-music_${APP_VERSION}_amd64.deb"
BUILD_DIR="dist/nuitka-linux"
PACKAGE_ROOT="dist/deb-root"
APP_ROOT="${PACKAGE_ROOT}/opt/163-music"

for asset in icon.png icon-48.png icon-64.png icon-128.png icon-256.png icon-512.png; do
  if [[ ! -f "assets/${asset}" ]]; then
    echo "missing assets/${asset}; the icon set is committed to the repository" >&2
    exit 1
  fi
done

if [[ "${DEB_ONLY}" == "0" ]]; then
  rm -rf "${BUILD_DIR}" "${PACKAGE_ROOT}" "dist/163-music"
  mkdir -p dist

  echo "==> Nuitka onefile ${APP_VERSION}"
  uv run nuitka \
    --onefile \
    --remove-output \
    --enable-plugin=pyside6 \
    --include-package=nm_shell \
    --include-package=loguru \
    --include-package=dbus_next \
    --include-module=webview.platforms.qt \
    --include-package-data=webview \
    --include-package=proxy_tools \
    --include-package=bottle \
    --include-package=qtpy \
    --include-qt-plugins=platforminputcontexts \
    --include-data-dir=ui=ui \
    --include-data-dir=assets=assets \
    --linux-icon=assets/icon.png \
    --output-dir="${BUILD_DIR}" \
    --output-filename=163-music \
    --assume-yes-for-downloads \
    main.py

  BINARY="${BUILD_DIR}/163-music"
  if [[ ! -x "${BINARY}" ]]; then
    echo "Nuitka did not produce ${BINARY}" >&2
    exit 1
  fi
  cp "${BINARY}" dist/163-music
  chmod 0755 dist/163-music

  echo "==> smoke test packaged onefile"
  ./dist/163-music --smoke-test || {
    echo "packaged smoke test failed" >&2
    exit 1
  }
else
  if [[ ! -x dist/163-music ]]; then
    echo "--deb-only requires dist/163-music" >&2
    exit 1
  fi
  BINARY="dist/163-music"
  rm -rf "${PACKAGE_ROOT}"
fi

echo "==> assemble DEB"
mkdir -p \
  "${PACKAGE_ROOT}/DEBIAN" \
  "${APP_ROOT}" \
  "${PACKAGE_ROOT}/usr/bin" \
  "${PACKAGE_ROOT}/usr/share/applications" \
  "${PACKAGE_ROOT}/usr/share/icons/hicolor/48x48/apps" \
  "${PACKAGE_ROOT}/usr/share/icons/hicolor/64x64/apps" \
  "${PACKAGE_ROOT}/usr/share/icons/hicolor/128x128/apps" \
  "${PACKAGE_ROOT}/usr/share/icons/hicolor/256x256/apps" \
  "${PACKAGE_ROOT}/usr/share/icons/hicolor/512x512/apps" \
  "${PACKAGE_ROOT}/usr/share/doc/163-music"

cp "${BINARY}" "${APP_ROOT}/163-music"
chmod 0755 "${APP_ROOT}/163-music"

cat > "${PACKAGE_ROOT}/usr/bin/163-music" <<'EOF'
#!/bin/sh
exec /opt/163-music/163-music "$@"
EOF
chmod 0755 "${PACKAGE_ROOT}/usr/bin/163-music"

cat > "${PACKAGE_ROOT}/usr/share/applications/163-music.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=网易云音乐
Name[zh_CN]=网易云音乐
GenericName=Music Player
Comment=非官方网易云音乐网页版桌面封装
Comment[zh_CN]=非官方网易云音乐网页版桌面封装
Exec=/usr/bin/163-music
Icon=163-music
Terminal=false
Categories=AudioVideo;Audio;Player;
Keywords=music;netease;163;player;
StartupNotify=true
StartupWMClass=163-music
EOF

for size in 48 64 128 256 512; do
  install -m 0644 "assets/icon-${size}.png" \
    "${PACKAGE_ROOT}/usr/share/icons/hicolor/${size}x${size}/apps/163-music.png"
done

cp README.md "${PACKAGE_ROOT}/usr/share/doc/163-music/README.md"
gzip -9 -n -c README.md > "${PACKAGE_ROOT}/usr/share/doc/163-music/README.md.gz"
cp LICENSE "${PACKAGE_ROOT}/usr/share/doc/163-music/LICENSE"
if [[ -d docs ]]; then
  cp -r docs "${PACKAGE_ROOT}/usr/share/doc/163-music/docs"
fi
cat > "${PACKAGE_ROOT}/usr/share/doc/163-music/copyright" <<'EOF'
This package is an unofficial wrapper around the official NetEase Cloud Music
web player. It is not affiliated with NetEase.

The source code is licensed under the MIT license; see LICENSE.

The NetEase Cloud Music name, icon, trademarks, page content, lyrics and music
remain the property of their respective owners. No cracking, DRM bypass,
downloading of paid music, ad removal or VIP bypass is provided.
EOF

INSTALLED_SIZE="$(du -sk "${PACKAGE_ROOT}" | cut -f1)"
cat > "${PACKAGE_ROOT}/DEBIAN/control" <<EOF
Package: 163-music
Version: ${APP_VERSION}
Section: sound
Priority: optional
Architecture: amd64
Maintainer: Pidbid <Pidbid@users.noreply.github.com>
Installed-Size: ${INSTALLED_SIZE}
Homepage: https://github.com/Pidbid/163_music
Depends: hicolor-icon-theme, libasound2t64 | libasound2, libatomic1, libbrotli1, libbz2-1.0, libc6 (>= 2.34), libdbus-1-3, libdrm2, libegl1, libexpat1, libffi8, libfontconfig1, libfreetype6, libgbm1, libgcc-s1, libgl1, libglib2.0-0t64 | libglib2.0-0, libglx0, libgssapi-krb5-2, libibus-1.0-5t64 | libibus-1.0-5, libnspr4, libnss3, libpng16-16t64 | libpng16-16, libpulse0, libstdc++6, libwayland-client0, libwayland-cursor0, libwayland-egl1, libx11-6, libx11-xcb1, libxau6, libxcb1, libxcb-cursor0, libxcb-dri3-0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-render0, libxcb-shape0, libxcb-shm0, libxcb-sync1, libxcb-util1, libxcb-xfixes0, libxcb-xinerama0, libxcb-xkb1, libxdmcp6, libxcomposite1, libxdamage1, libxext6, libxfixes3, libxkbcommon0, libxkbcommon-x11-0, libxkbfile1, libxrandr2, libxrender1, libxshmfence1, libxtst6
Recommends: gstreamer1.0-plugins-base, gstreamer1.0-plugins-good, gstreamer1.0-plugins-bad, gstreamer1.0-plugins-ugly, gstreamer1.0-libav, libnotify4
Description: 非官方网易云音乐网页版桌面封装
 仅封装网易云音乐官方在线页面，不提供任何破解、下载、去广告或 VIP 绕过功能。
 支持无边框窗口、系统托盘、MPRIS 媒体控制、主题跟随标题栏和可选桌面歌词。
EOF

dpkg-deb --root-owner-group --build "${PACKAGE_ROOT}" "dist/${DEB_NAME}"
desktop-file-validate "${PACKAGE_ROOT}/usr/share/applications/163-music.desktop"
dpkg-deb --info "dist/${DEB_NAME}"
sha256sum "dist/163-music" "dist/${DEB_NAME}"

echo "Linux build complete:"
echo "  dist/163-music"
echo "  dist/${DEB_NAME}"
