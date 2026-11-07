@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Reworkl.ps1" -CheckOnly %*
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%
