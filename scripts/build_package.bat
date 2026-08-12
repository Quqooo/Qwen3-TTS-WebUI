@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set ROOT=%~dp0..
cd /d "%ROOT%"

set "VENV=%ROOT%\.venv-build"
set "VENV_PY=%VENV%\Scripts\python.exe"

:: build frontend
cd /d "%ROOT%\frontend"
call pnpm install >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pnpm install failed
    pause
    exit /b 1
)
call pnpm build
if errorlevel 1 (
    echo [ERROR] pnpm build failed
    pause
    exit /b 1
)

:: prepare build env
if not exist "%VENV_PY%" (
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo [ERROR] Failed to create the build virtual environment
        pause
        exit /b 1
    )
)
"%VENV_PY%" -m pip install --disable-pip-version-check -q -e "%ROOT%" pyinstaller
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

:: package
cd /d "%ROOT%"
for /f "tokens=3" %%V in ('findstr /C:"version = " "%ROOT%\pyproject.toml"') do set "APP_VERSION=%%V"
set "APP_VERSION=%APP_VERSION:"=%"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" (
    set "APP_ARCH=arm64"
) else (
    set "APP_ARCH=x86_64"
)
set "ARTIFACT=Qwen3-TTS-WebUI-v%APP_VERSION%-win-%APP_ARCH%"
"%VENV_PY%" -m PyInstaller --clean --noconfirm "packaging\Qwen3-TTS-WebUI.spec"
if errorlevel 1 (
    echo [ERROR] PyInstaller packaging failed
    pause
    exit /b 1
)

for %%F in ("%ROOT%\dist\%ARTIFACT%.exe") do set "SIZE_KB=%%~zF"
set /a SIZE_MB=%SIZE_KB% / 1048576
echo Build completed: dist\%ARTIFACT%.exe (%SIZE_MB% MB)
pause
exit /b 0
