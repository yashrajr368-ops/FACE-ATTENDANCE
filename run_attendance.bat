@echo off
title Face Recognition Attendance System
cd /d "e:\LEGAL_AI\casify\attendance"

echo ===================================================
echo   Launching Face Recognition Attendance System
echo ===================================================

:: Check if server is already running on port 5000
netstat -ano | findstr :5000 | findstr LISTENING >nul
if %ERRORLEVEL% equ 0 (
    echo [*] Server is already active on port 5000!
) else (
    echo [*] Starting Flask web server...
    start "" python app.py
    timeout /t 2 /nobreak >nul
)

echo [*] Opening browser to http://127.0.0.1:5000 ...
start http://127.0.0.1:5000

echo ===================================================
echo   System is ready!
echo   Login: admin / admin123
echo ===================================================
timeout /t 5
