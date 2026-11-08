@echo off
setlocal EnableExtensions DisableDelayedExpansion
title REWORKL - READ ONLY CRASH COLLECTION
color 0B
echo ==============================================================
echo   REWORKL - COLLECT CURRENT CRASH - NO REINSTALL
echo ==============================================================
echo This will not launch, stop, reinstall or redirect the game.
echo It only creates its own diagnostic text and ZIP beside this BAT.
echo.
if not exist "%~dp0Reworkl-Crash-Diagnostics.ps1" (
  echo ERROR: Extract this WHOLE small diagnostics ZIP first.
  if not defined REWORKL_NO_PAUSE pause
  exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Reworkl-Crash-Diagnostics.ps1" %*
set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" echo Collection finished. Send REWORKL_CRASH_DIAGNOSTICS_...zip from this folder.
if not "%RESULT%"=="0" echo Collection error. Send a screenshot of this window.
echo Collection is NOT a claim that the game loaded or the crash was fixed.
if not defined REWORKL_NO_PAUSE pause
exit /b %RESULT%
