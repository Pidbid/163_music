#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "build_macos.sh must run on macOS" >&2
  exit 1
fi

for command_name in uv; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "missing build command: ${command_name}" >&2
    exit 1
  fi
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

APP_VERSION="$(uv run python -c 'from nm_shell.version import __version__; print(__version__)')"
BUILD_DIR="dist/nuitka-macos"
APP_BUNDLE="${BUILD_DIR}/163-music.app"
EXECUTABLE="${APP_BUNDLE}/Contents/MacOS/163-music"
ZIP="dist/163-music-macos.zip"

echo "==> Nuitka app bundle ${APP_VERSION} (macOS)"
rm -rf "${BUILD_DIR}" "${ZIP}"
mkdir -p dist

uv run nuitka \
  --mode=app \
  --remove-output \
  --enable-plugin=pyside6 \
  --include-package=nm_shell \
  --include-package=loguru \
  --include-package=dbus_next \
  --include-package=proxy_tools \
  --include-package=bottle \
  --include-module=webview.platforms.cocoa \
  --include-package-data=webview \
  --include-data-dir=ui=ui \
  --include-data-dir=assets=assets \
  --macos-app-name=163-music \
  --macos-app-version="${APP_VERSION}" \
  --macos-app-icon=assets/icon.icns \
  --macos-app-category-type=public.app-category.music \
  --output-filename=163-music \
  --output-dir="${BUILD_DIR}" \
  --assume-yes-for-downloads \
  main.py

if [[ ! -x "${EXECUTABLE}" ]]; then
  echo "Nuitka did not produce ${EXECUTABLE}" >&2
  exit 1
fi

echo "==> smoke test app bundle"
"${EXECUTABLE}" --smoke-test

echo "==> package .app"
ditto -c -k --sequesterRsrc --keepParent "${APP_BUNDLE}" "${ZIP}"

echo "macOS build complete: ${ZIP}"
