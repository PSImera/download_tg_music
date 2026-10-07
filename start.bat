@echo off
title Download TG Music
echo ========================================
echo   Download TG Music - starting...
echo ========================================
echo.

call "%~dp0.venv\Scripts\activate.bat"
python "%~dp0download_tg_music.py"

echo.
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Script exited with code %ERRORLEVEL%
) else (
    echo [OK] Script finished.
)
pause
