@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

cd /d "%~dp0"

echo.
echo ========================================
echo   163-music - Windows onefile build
echo ========================================
echo.

if not exist "assets\icon.ico" (
    echo Missing assets\icon.ico; the icon set is committed to the repository.
    exit /b 1
)

if not exist "dist" mkdir dist

for /f "usebackq delims=" %%v in (`uv run python -c "from nm_shell.version import __version__; print(__version__)"`) do (
    if not defined APP_VERSION set "APP_VERSION=%%v"
)
if not defined APP_VERSION (
    echo Could not read the application version from nm_shell/version.py
    exit /b 1
)

echo Building 163-music %APP_VERSION% with Nuitka (onefile)...
uv run nuitka ^
  --mingw64 ^
  --onefile ^
  --remove-output ^
  --windows-console-mode=disable ^
  --enable-plugin=pyside6 ^
  --include-package=nm_shell ^
  --include-package=loguru ^
  --include-package=dbus_next ^
  --include-package=proxy_tools ^
  --include-package=bottle ^
  --include-package=pythonnet ^
  --include-package-data=pythonnet ^
  --include-package=clr_loader ^
  --include-package-data=clr_loader ^
  --include-module=webview.platforms.winforms ^
  --include-package-data=webview ^
  --include-data-dir=ui=ui ^
  --include-data-dir=assets=assets ^
  --windows-icon-from-ico=assets\icon.ico ^
  --windows-company-name="Pidbid" ^
  --windows-product-name="163-music" ^
  --windows-file-version=%APP_VERSION% ^
  --windows-product-version=%APP_VERSION% ^
  --windows-file-description="Unofficial NetEase Cloud Music web player shell" ^
  --output-dir=dist\nuitka-windows ^
  --output-filename=163-music.exe ^
  --assume-yes-for-downloads ^
  main.py

if errorlevel 1 (
    echo.
    echo Build failed.
    exit /b 1
)

if not exist "dist\nuitka-windows\163-music.exe" (
    echo Nuitka did not produce dist\nuitka-windows\163-music.exe
    exit /b 1
)

echo.
echo Smoke test:
dist\nuitka-windows\163-music.exe --smoke-test
if errorlevel 1 (
    echo Packaged smoke test failed.
    exit /b 1
)

echo.
echo Build complete: dist\nuitka-windows\163-music.exe
exit /b 0
