@echo off
setlocal EnableExtensions DisableDelayedExpansion
color 0B
echo ==============================================================
echo   REWORKL - PATCHLAUNCHER - BAT / NO DLC
echo ==============================================================
echo.
if not exist "%~dp0Reworkl-Bat.ps1" (
  echo ERROR: Reworkl-Bat.ps1 is missing. Extract the WHOLE toolkit ZIP.
  if not defined REWORKL_NO_PAUSE pause
  exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Reworkl-Bat.ps1" -Action PatchLauncher %*
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" echo FAILED or NOT CONFIRMED. Read the message above.
if not defined REWORKL_NO_PAUSE pause
exit /b %RESULT%
