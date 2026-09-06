@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title RecordGuard Web

echo ========================================
echo       RecordGuard Web - Local Launcher
echo ========================================
echo.

where py >nul 2>&1
if not errorlevel 1 (set "PY=py -3") else (set "PY=python")

%PY% --version >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python 3 was not found.
  echo Install Python 3.10+ and enable the Python launcher/PATH.
  pause
  exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
  echo ERROR: npm was not found.
  echo Install Node.js LTS, then run this launcher again.
  pause
  exit /b 1
)

if not exist "apps\web\package.json" (
  echo ERROR: Web application files are missing.
  pause
  exit /b 1
)

if not exist "apps\web\node_modules" (
  echo Installing web dependencies with npm ci...
  cd /d "%~dp0apps\web"
  call npm ci --no-audit --no-fund
  if errorlevel 1 (
    echo.
    echo ERROR: Web dependencies could not be installed.
    echo Check your internet connection and Node/npm installation.
    pause
    exit /b 1
  )
  cd /d "%~dp0"
)

python -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
  echo Installing Python web dependencies...
  %PY% -m pip install -r requirements-web.txt
  if errorlevel 1 (
    echo.
    echo ERROR: Python web dependencies could not be installed.
    pause
    exit /b 1
  )
)

echo Starting RecordGuard API on http://127.0.0.1:8000 ...
start "RecordGuard API" cmd /k "cd /d "%~dp0" && %PY% run_api.py"

set "READY=0"
for /l %%N in (1,1,30) do (
  powershell -NoProfile -Command "$r=try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 1 } catch { $null }; if ($r -and $r.StatusCode -eq 200) { exit 0 } else { exit 1 }" >nul 2>&1
  if not errorlevel 1 (
    set "READY=1"
    goto :api_ready
  )
  timeout /t 1 /nobreak >nul
)

:api_ready
if "%READY%"=="0" echo WARNING: API health endpoint was not confirmed; the web app may still start if the API is slow to initialize.

echo Starting RecordGuard Web on http://localhost:3000 ...
start "RecordGuard Web" cmd /k "cd /d "%~dp0apps\web" && npm run dev"
timeout /t 3 /nobreak >nul
start "" "http://localhost:3000"

echo.
echo RecordGuard Web is starting.
echo API: http://127.0.0.1:8000
echo Web: http://localhost:3000
endlocal
