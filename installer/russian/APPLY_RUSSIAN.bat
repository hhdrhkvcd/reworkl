@echo off
setlocal EnableExtensions DisableDelayedExpansion
color 0B
echo REWORKL - RUSSIAN TEXT FIX RU2
echo Close HOI4 first. Extract the WHOLE new ZIP.
echo This does NOT change your launcher, settings or saves.
echo.
if not exist "%~dp0Reworkl-Russian.ps1" (
  echo ERROR: Reworkl-Russian.ps1 is missing. Extract the whole ZIP.
  if not defined REWORKL_NO_PAUSE pause
  exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Reworkl-Russian.ps1" %*
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" echo FAILED. Send REWORKL_RUSSIAN_REPORT.txt, not a folder screenshot.
if not defined REWORKL_NO_PAUSE pause
exit /b %RESULT%
