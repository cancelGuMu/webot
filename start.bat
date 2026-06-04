@echo off
title WeChat Bot - One-Click Launcher
setlocal enabledelayedexpansion
cd /d "%~dp0"

:: Try to set UTF-8 codepage (suppress errors if it fails)
chcp 65001 > nul 2>&1

echo ============================================
echo   WeChat Bot - One-Click Launcher
echo   (WeFlow will auto-start in background)
echo ============================================
echo.

:: Find Python - try multiple command names
set PYTHON=
for %%p in (python python3 py) do (
    if "!PYTHON!"=="" (
        %%p --version > nul 2>&1
        if not errorlevel 1 set PYTHON=%%p
    )
)

if "%PYTHON%"=="" (
    echo [Error] Python not found. Please install Python 3.10+
    echo         https://www.python.org/downloads/
    echo         Check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

:: Launch the Python launcher
%PYTHON% launcher.py %*
pause
exit /b 0
