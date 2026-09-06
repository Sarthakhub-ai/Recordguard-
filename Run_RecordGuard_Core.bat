@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
  py -3 main.py
) else (
  python main.py
)
if errorlevel 1 (
  echo.
  echo RecordGuard Core stopped with an error.
  if exist startup_log.txt echo See startup_log.txt for details.
  pause
)
endlocal
