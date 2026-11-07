@echo off
setlocal EnableExtensions DisableDelayedExpansion
title REWORKL WORLD 2026 - INSTALL AND START
color 0B
echo ==============================================================
echo   REWORKL WORLD 2026 - FULL UPDATE AND START
echo ==============================================================
echo Close HOI4 and Paradox Launcher. Keep Steam running.
echo This button installs the NEW full mod before launching it.
echo.
if not exist "%~dp0Reworkl-Bat.ps1" (
  echo ERROR: Reworkl-Bat.ps1 is missing. Extract the WHOLE ZIP.
  if not defined REWORKL_NO_PAUSE pause
  exit /b 1
)
if not exist "%~dp0reworkl\descriptor.mod" (
  echo ERROR: FULL 2026 ZIP REQUIRED. A small toolkit has no world map.
  if not defined REWORKL_NO_PAUSE pause
  exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Reworkl-Bat.ps1" -Action Start2026 -Source "%~dp0reworkl" -ReportPath "%~dp0REWORKL_START_RESULT.txt" %*
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" echo FAILED or NOT CONFIRMED. Send REWORKL_START_RESULT.txt or the DIAGNOSTICS ZIP beside this BAT.
if not defined REWORKL_NO_PAUSE pause
exit /b %RESULT%
