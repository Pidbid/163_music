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

echo "==> Nuitka onefile ${APP_VERSION} (macOS)"
rm -rf "${BUILD_DIR}" "dist/${APP_VERSION}-macos"
mkdir -p dist

uv run nuitka \
  --onefile \
  --remove-output \
  --enable-plugin=pyside6 \
  --include-package=nm_shell \
  --include-package=loguru \
  --include-package=dbus_next \
  --include-package=proxy_tools \
  --include-package=bottle \
  --include-package=qtpy \
  --include-module=webview.platforms.cocoa \
  --include-package-data=webview \
  --include-data-dir=ui=ui \
  --include-data-dir=assets=assets \
  --output-dir="${BUILD_DIR}" \
  --output-filename=163-music \
  --assume-yes-for-downloads \
  main.py

BINARY="${BUILD_DIR}/163-music"
if [[ ! -x "${BINARY}" ]]; then
  echo "Nuitka did not produce ${BINARY}" >&2
  exit 1
fi

echo "==> smoke test packaged onefile"
"${BINARY}" --smoke-test

echo "macOS build complete: ${BINARY}"
