@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title RecordGuard

echo ========================================
echo          RecordGuard
echo ========================================
echo.

set "PYTHON_CMD="
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
) else (
    python --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo ERROR: Python 3 was not found.
    echo.
    echo Install Python 3 from python.org and make sure the Python
    echo launcher or "Add Python to PATH" option is enabled.
    echo.
    pause
    exit /b 1
)

echo Using %PYTHON_CMD%
echo Checking required packages...

%PYTHON_CMD% -c "import cryptography, PIL, pytesseract, pypdf, reportlab" >nul 2>&1
if errorlevel 1 (
    echo Some required Python packages are missing.
    echo Installing packages from requirements.txt...
    echo.
    %PYTHON_CMD% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: Required packages could not be installed.
        echo Check your internet connection and Python/pip installation.
        echo.
        pause
        exit /b 1
    )
)

echo.
echo Starting RecordGuard...
echo If the application does not open, check startup_log.txt.
echo.

%PYTHON_CMD% main.py
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo ========================================
    echo RecordGuard stopped with an error.
    echo ========================================
    if exist startup_log.txt (
        echo.
        echo Startup details:
        type startup_log.txt
    )
    echo.
    pause
)

endlocal & exit /b %EXIT_CODE%
