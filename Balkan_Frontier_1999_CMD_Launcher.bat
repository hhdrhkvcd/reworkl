@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
mode con: cols=100 lines=38 >nul 2>&1
title BALKAN FRONTIER 1999 // DIRECT COMMAND LAUNCHER
color 0B
set "ROOT=%~dp0"
set "WORK=%TEMP%\BF1999_launcher"
if not exist "%WORK%" md "%WORK%" >nul 2>&1

:MENU
cls
echo.
echo  ====================================================================================================
echo.
echo       ██████╗  █████╗ ██╗     ██╗  ██╗ █████╗ ███╗   ██╗
echo       ██╔══██╗██╔══██╗██║     ██║ ██╔╝██╔══██╗████╗  ██║
echo       ██████╔╝███████║██║     █████╔╝ ███████║██╔██╗ ██║
echo       ██╔══██╗██╔══██╗██║     ██║ ██╔═╝ ██╔══██║██║╚██╗██║
echo       ██████╔╝██║  ██║███████╗██║  ██╗██║  ██║██║ ╚████║
echo       ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝
echo.
echo                         FRONTIER 1999 // DIRECT COMMAND CENTER
echo.
echo  ====================================================================================================
echo       BUILD: HOI4 1.20.x     MODE: DIRECT EXE     PARADOX LAUNCHER: BYPASSED
echo  ====================================================================================================
echo.
echo       [1] INSTALL / UPDATE MOD AND LAUNCH GAME DIRECTLY
echo       [2] INSTALL / UPDATE MOD ONLY
echo       [3] SYSTEM DIAGNOSTICS
echo       [4] OPEN MOD INSTALLATION FOLDER
echo       [0] EXIT
echo.
set "CHOICE="
set /p "CHOICE=  BF1999@COMMAND> "
if "%CHOICE%"=="1" goto INSTALL_LAUNCH
if "%CHOICE%"=="2" goto INSTALL_ONLY
if "%CHOICE%"=="3" goto DIAG
if "%CHOICE%"=="4" goto OPEN_MOD
if "%CHOICE%"=="0" goto EXIT
echo [!] Unknown command.
ping 127.0.0.1 -n 2 >nul
goto MENU

:INSTALL_LAUNCH
cls
echo.
echo  [BF1999] PREPARING MOD FILES...
call :INSTALL_MOD
if errorlevel 1 goto ERROR_PAUSE
call :FIND_GAME
if errorlevel 1 goto ERROR_PAUSE
echo.
echo  [OK] MOD INSTALLED
echo  [OK] GAME EXECUTABLE FOUND
echo  [OK] DIRECT START CONFIGURED
echo.
echo  Launching hoi4.exe directly. Paradox Launcher will not be opened by this script.
ping 127.0.0.1 -n 3 >nul
pushd "%GAME_DIR%"
start "Balkan Frontier 1999" "%GAME_EXE%" "-mod=%MOD_DESC%"
popd
echo.
echo  [OK] Launch command sent to Windows.
echo  If the game still crashes, send error.log and exception.txt.
echo.
pause
goto MENU

:INSTALL_ONLY
cls
echo.
echo  [BF1999] INSTALL / UPDATE
call :INSTALL_MOD
if errorlevel 1 goto ERROR_PAUSE
echo.
echo  [OK] Mod installed.
echo  [INFO] Choose option 1 to launch HOI4 directly.
echo.
pause
goto MENU

:INSTALL_MOD
call :RESOLVE_MOD
if errorlevel 1 exit /b 1
call :GET_DOCUMENTS
if not defined DOCS (
 echo [ERROR] Windows Documents folder could not be determined.
 exit /b 1
)
set "MODROOT=%DOCS%\Paradox Interactive\Hearts of Iron IV\mod"
set "MODDEST=%MODROOT%\Balkan_Frontier_1999"
set "MOD_DESC=%MODROOT%\Balkan_Frontier_1999.mod"
if not exist "%MODROOT%" md "%MODROOT%" 2>nul
if not exist "%MODROOT%" (
 echo [ERROR] Cannot create the HOI4 mod directory:
 echo         %MODROOT%
 echo [HELP] Check that Documents is writable or install HOI4 once.
 exit /b 1
)
echo  [1/3] Copying mod files...
robocopy "%MODSRC%" "%MODDEST%" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NC /NS /NP >nul
if errorlevel 8 (
 echo [ERROR] Windows denied copying files into the HOI4 mod directory.
 echo [HELP] Close HOI4 and the Paradox Launcher, then try again.
 exit /b 1
)
echo  [2/3] Creating local HOI4 descriptor...
set "MODDEST_FWD=%MODDEST:\=/%"
(
 echo name="Balkan Frontier 1999"
 echo path="%MODDEST_FWD%"
 echo version="0.1.5"
 echo supported_version="1.20.*"
 echo replace_path="history/states"
 echo replace_path="map"
) >"%MOD_DESC%"
if not exist "%MOD_DESC%" (
 echo [ERROR] Cannot write mod descriptor: %MOD_DESC%
 exit /b 1
)
echo  [3/3] Verifying important files...
if not exist "%MODDEST%\descriptor.mod" (
 echo [ERROR] Installed descriptor.mod is missing.
 exit /b 1
)
if not exist "%MODDEST%\common\bookmarks\BF1999_bookmark.txt" (
 echo [ERROR] Bookmark file is missing.
 exit /b 1
)
if not exist "%MODDEST%\common\country_tags\zzzz_bf1999_countries.txt" (
 echo [ERROR] Country tags file is missing.
 exit /b 1
)
echo  [OK] Source: %MODSRC%
echo  [OK] Installed: %MODDEST%
exit /b 0

:RESOLVE_MOD
set "MODSRC="
echo  [SEARCH] Checking only the launcher folder and nearby package files...
if exist "%ROOT%Balkan_Frontier_1999\descriptor.mod" set "MODSRC=%ROOT%Balkan_Frontier_1999"
if defined MODSRC exit /b 0
for /d %%D in ("%ROOT%*") do (
 if exist "%%~fD\descriptor.mod" if exist "%%~fD\common\bookmarks\BF1999_bookmark.txt" set "MODSRC=%%~fD"
 if exist "%%~fD\Balkan_Frontier_1999\descriptor.mod" set "MODSRC=%%~fD\Balkan_Frontier_1999"
)
if defined MODSRC exit /b 0
set "PACKAGE_ZIP="
for %%Z in ("%ROOT%Balkan_Frontier_1999_HOI4_1.20_*.zip") do if exist "%%~fZ" set "PACKAGE_ZIP=%%~fZ"
if not defined PACKAGE_ZIP (
 echo.
 echo  [HELP] Put the FULL mod ZIP in the same folder as this BAT,
 echo         or type the full path to the ZIP below.
 set /p "PACKAGE_ZIP=  ZIP path> "
 set "PACKAGE_ZIP=%PACKAGE_ZIP:"=%"
)
if not defined PACKAGE_ZIP (
 echo [ERROR] No full ZIP package was selected.
 exit /b 1
)
if not exist "%PACKAGE_ZIP%" (
 echo [ERROR] ZIP file not found: %PACKAGE_ZIP%
 exit /b 1
)
where tar.exe >nul 2>&1
if errorlevel 1 (
 echo [ERROR] Windows tar.exe was not found.
 echo [HELP] Right-click the ZIP, choose Extract All, then put this BAT beside
 echo        the extracted Balkan_Frontier_1999 folder and run it again.
 exit /b 1
)
set "EXTRACT_DIR=%WORK%\package"
if exist "%EXTRACT_DIR%" rmdir /s /q "%EXTRACT_DIR%" 2>nul
md "%EXTRACT_DIR%" 2>nul
if not exist "%EXTRACT_DIR%" (
 echo [ERROR] Cannot create temporary extraction folder: %EXTRACT_DIR%
 exit /b 1
)
echo  [EXTRACT] Unpacking the selected ZIP with Windows tar...
tar.exe -xf "%PACKAGE_ZIP%" -C "%EXTRACT_DIR%"
if errorlevel 1 (
 echo [ERROR] Could not extract the ZIP package.
 echo [HELP] Extract the ZIP manually with Windows File Explorer.
 exit /b 1
)
if exist "%EXTRACT_DIR%\Balkan_Frontier_1999\descriptor.mod" set "MODSRC=%EXTRACT_DIR%\Balkan_Frontier_1999"
if not defined MODSRC (
 for /d %%D in ("%EXTRACT_DIR%*") do (
  if exist "%%~fD\descriptor.mod" if exist "%%~fD\common\bookmarks\BF1999_bookmark.txt" set "MODSRC=%%~fD"
  if exist "%%~fD\Balkan_Frontier_1999\descriptor.mod" set "MODSRC=%%~fD\Balkan_Frontier_1999"
 )
)
if not defined MODSRC (
 echo [ERROR] ZIP extracted, but expected mod files were not found.
 exit /b 1
)
echo  [OK] Mod source found: %MODSRC%
exit /b 0

:GET_DOCUMENTS
set "DOCS="
for /f "tokens=2,*" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v Personal 2^>nul ^| find /i "Personal"') do set "DOCS=%%B"
if not defined DOCS set "DOCS=%USERPROFILE%\Documents"
call set "DOCS=%DOCS%"
exit /b 0

:FIND_GAME
cls
echo.
echo  [BF1999] SEARCHING FOR HEARTS OF IRON IV...
set "GAME_EXE="
set "FIND_PS1=%ROOT%Find-HOI4.ps1"
if not exist "%FIND_PS1%" set "FIND_PS1=%WORK%\package\Find-HOI4.ps1"
if exist "%FIND_PS1%" powershell -NoProfile -ExecutionPolicy Bypass -File "%FIND_PS1%" >"%WORK%\gamepath.txt" 2>nul
if exist "%WORK%\gamepath.txt" set /p "GAME_EXE="<"%WORK%\gamepath.txt"
if not defined GAME_EXE (
 echo [INFO] Automatic detection did not find the game.
 set /p "GAME_EXE=  Enter full path to hoi4.exe> "
 set "GAME_EXE=%GAME_EXE:"=%"
)
if not exist "%GAME_EXE%" (
 echo [ERROR] hoi4.exe was not found: %GAME_EXE%
 exit /b 1
)
for %%G in ("%GAME_EXE%") do set "GAME_DIR=%%~dpG"
exit /b 0

:DIAG
cls
echo.
echo  ========================== BF1999 SYSTEM DIAGNOSTICS ==========================
call :RESOLVE_MOD
if errorlevel 1 (echo [ERROR] Mod source not found.) else (echo [OK] Mod source: %MODSRC%)
echo.
echo  Diagnostics checks paths and files only; this is not a full in-game test.
echo  ================================================================================
pause
goto MENU

:OPEN_MOD
call :GET_DOCUMENTS
if defined DOCS if exist "%DOCS%\Paradox Interactive\Hearts of Iron IV\mod" start "" "%DOCS%\Paradox Interactive\Hearts of Iron IV\mod"
goto MENU

:ERROR_PAUSE
echo.
echo  [FAILED] Operation stopped. No game process was started.
echo.
pause
goto MENU

:EXIT
cls
echo [BF1999] COMMAND SESSION CLOSED.
exit /b
