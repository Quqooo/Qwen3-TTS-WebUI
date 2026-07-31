@echo off
chcp 65001 >nul
setlocal

set ROOT=%~dp0
cd /d "%ROOT%"
set "FRONTEND=%ROOT%frontend"
set "STATIC=%ROOT%backend\static"
set "VENV=%ROOT%.venv"
set "VENV_PY=%VENV%\Scripts\python.exe"

if not exist "%VENV_PY%" (
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment. Check that Python is installed and in PATH.
        pause
        exit /b 1
    )
)

"%VENV_PY%" -m pip install -e "%ROOT%" >nul 2>&1

if not exist "%FRONTEND%\node_modules" (
    cd /d "%FRONTEND%"
    call pnpm install
    if errorlevel 1 (
        echo [ERROR] pnpm install failed. Check that pnpm is installed and in PATH.
        pause
        exit /b 1
    )
)

if not exist "%STATIC%\index.html" goto :build_frontend
powershell -NoProfile -Command "$newer = Get-ChildItem -Recurse '%FRONTEND%\src','%FRONTEND%\public','%FRONTEND%\index.html','%FRONTEND%\package.json' -ErrorAction SilentlyContinue | Where-Object { -not $_.PSIsContainer -and $_.LastWriteTime -gt (Get-Item '%STATIC%\index.html').LastWriteTime }; if ($newer.Count -gt 0) { exit 1 } else { exit 0 }"
if errorlevel 1 goto :build_frontend
goto :skip_build

:build_frontend
cd /d "%FRONTEND%"
call pnpm build
if errorlevel 1 (
    echo [ERROR] Frontend build failed.
    pause
    exit /b 1
)
:skip_build

cd /d "%ROOT%"
"%VENV_PY%" -m uvicorn backend.main:app --port 8000 --host localhost
pause
endlocal
