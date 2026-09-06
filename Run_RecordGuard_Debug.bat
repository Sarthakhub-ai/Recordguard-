@echo off
setlocal
cd /d "%~dp0"
title RecordGuard - Diagnostic Launcher

echo RecordGuard diagnostic launcher
echo ================================
echo.

where py >nul 2>&1
if not errorlevel 1 (
    set "PY=py -3"
) else (
    set "PY=python"
)

echo [1/4] Python:
%PY% --version
if errorlevel 1 goto :fail

echo.
echo [2/4] Tkinter:
%PY% -c "import tkinter; print('Tkinter OK')"
if errorlevel 1 goto :fail

echo.
echo [3/4] Core imports:
%PY% -c "import cryptography, PIL, pytesseract, pypdf, reportlab; import database, functions, core_ui; print('Core imports OK')"
if errorlevel 1 goto :fail

echo.
echo [4/4] Application:
%PY% main.py
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" goto :fail

echo.
echo RecordGuard closed normally.
pause
exit /b 0

:fail
echo.
echo DIAGNOSTIC FAILURE
echo ------------------
if exist startup_log.txt (
  echo.
  echo startup_log.txt:
  type startup_log.txt
)
echo.
echo Exit code: %ERRORLEVEL%
pause
exit /b 1

