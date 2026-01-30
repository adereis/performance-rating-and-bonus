@echo off
REM Quick start script for Performance Rating System (Windows)

echo.
echo ==========================================
echo   Performance Rating System - Quick Start
echo ==========================================
echo.

REM Check for Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Error: Python is not installed or not in PATH.
    echo Please install Python 3.9 or later from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

REM Check Python version
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VERSION=%%v
echo Found Python %PY_VERSION%

REM Get script directory
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM Create and use virtual environment (use relative path)
set VENV_DIR=.venv

if not exist "%VENV_DIR%" (
    echo.
    echo Creating virtual environment...
    python -m venv "%VENV_DIR%"
    if %ERRORLEVEL% neq 0 (
        echo Error: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo Virtual environment created
)

REM Activate virtual environment
call "%VENV_DIR%\Scripts\activate.bat"
if %ERRORLEVEL% neq 0 (
    echo Error: Failed to activate virtual environment
    pause
    exit /b 1
)

REM Install dependencies
echo.
echo Installing dependencies...
pip install --quiet --upgrade pip
if %ERRORLEVEL% neq 0 (
    echo Warning: pip upgrade had issues, continuing anyway
)

pip install --quiet -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo Error: Failed to install dependencies
    pause
    exit /b 1
)
echo Dependencies installed successfully

set HOST=127.0.0.1
set PORT=5000
set URL=http://%HOST%:%PORT%

echo.
echo Starting application...
echo.
echo ==========================================
echo   Open your browser to: %URL%
echo   Press Ctrl+C to stop
echo ==========================================
echo.

REM Open browser
start "" "%URL%"

REM Run the application
python app.py
