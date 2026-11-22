@echo off
setlocal
chcp 65001 >nul
title BALKAN FRONTIER 1999 - START WITH MOD
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0BF1999_ForceLaunch.ps1"
if errorlevel 1 pause
endlocal
