@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
    py -3 seed_demo_data.py
) else (
    python seed_demo_data.py
)
if errorlevel 1 (
    echo.
    echo Demo-data setup failed. Read the message above.
) else (
    echo.
    echo Demo-data setup completed successfully.
)
pause
endlocal
