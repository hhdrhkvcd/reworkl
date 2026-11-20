@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
mode con: cols=100 lines=38 >nul 2>&1
title BALKAN FRONTIER 1999 // DIRECT COMMAND LAUNCHER
color 0B
set "ROOT=%~dp0"
set "MODSRC=%ROOT%Balkan_Frontier_1999"
set "WORK=%TEMP%\BF1999_launcher"
if not exist "%WORK%" md "%WORK%" >nul 2>&1

:BOOT
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
call :wait 1

:MENU
cls
echo.
echo  +--------------------------------------------------------------------------------------------------+
echo  ^|                         BALKAN FRONTIER 1999 // OPERATIONS TERMINAL                              ^|
echo  +--------------------------------------------------------------------------------------------------+
echo.
echo       [1] INSTALL / UPDATE MOD AND LAUNCH GAME DIRECTLY
echo       [2] INSTALL / UPDATE MOD ONLY
echo       [3] SYSTEM DIAGNOSTICS
echo       [4] OPEN MOD INSTALLATION FOLDER
echo       [0] EXIT
echo.
echo  ----------------------------------------------------------------------------------------------------
set "CHOICE="
set /p "CHOICE=  BF1999@COMMAND> "
if "%CHOICE%"=="1" goto INSTALL_LAUNCH
if "%CHOICE%"=="2" goto INSTALL_ONLY
if "%CHOICE%"=="3" goto DIAG
if "%CHOICE%"=="4" goto OPEN_MOD
if "%CHOICE%"=="0" goto EXIT
echo.
echo  [!] UNKNOWN COMMAND.
call :wait 2
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
echo  -------------------------------------------------------------------------------
echo  Launching hoi4.exe directly. Paradox Launcher will not be opened by this script.
echo  -------------------------------------------------------------------------------
call :wait 2
pushd "%GAME_DIR%"
start "Balkan Frontier 1999" "%GAME_EXE%" "-mod=%MOD_DESC%"
popd
echo.
echo  [OK] Launch command sent to Windows.
echo  If the game does not load the mod, send me the new error.log and launcher.log.
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
echo  [OK] Mod files copied and descriptor created.
echo  [INFO] Use option 1 to start the game directly.
echo.
pause
goto MENU

:INSTALL_MOD
if not exist "%MODSRC%\descriptor.mod" (
 echo [ERROR] Folder Balkan_Frontier_1999 was not found beside this BAT file.
 echo [INFO] Extract the complete package, keeping the folder structure.
 exit /b 1
)
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('MyDocuments')" 2^>nul`) do set "DOCS=%%P"
if not defined DOCS (
 echo [ERROR] Cannot locate Windows Documents folder.
 exit /b 1
)
set "MODROOT=%DOCS%\Paradox Interactive\Hearts of Iron IV\mod"
set "MODDEST=%MODROOT%\Balkan_Frontier_1999"
set "MOD_DESC=%MODROOT%\Balkan_Frontier_1999.mod"
if not exist "%MODROOT%" md "%MODROOT%" >nul 2>&1
if not exist "%MODROOT%" (
 echo [ERROR] Cannot create mod folder: %MODROOT%
 exit /b 1
)
echo  [1/3] Copying mod content...
robocopy "%MODSRC%" "%MODDEST%" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NC /NS /NP >nul
if errorlevel 8 (
 echo [ERROR] Robocopy failed while copying mod files.
 exit /b 1
)
echo  [2/3] Writing clean HOI4 1.20 descriptor...
set "MODDEST_FWD=%MODDEST:\=/%"
(
 echo name="Balkan Frontier 1999"
 echo path="%MODDEST_FWD%"
 echo version="0.1.3"
 echo supported_version="1.20.*"
 echo replace_path="history/states"
 echo replace_path="map"
)>"%MOD_DESC%"
if not exist "%MOD_DESC%" (
 echo [ERROR] Could not write mod descriptor.
 exit /b 1
)
echo  [3/3] Verifying key files...
if not exist "%MODDEST%\common\bookmarks\BF1999_bookmark.txt" (
 echo [ERROR] Bookmark file is missing after installation.
 exit /b 1
)
if not exist "%MODDEST%\common\country_tags\zzzz_bf1999_countries.txt" (
 echo [ERROR] Country tags file is missing after installation.
 exit /b 1
)
echo  [OK] Installed to: %MODDEST%
exit /b 0

:FIND_GAME
cls
echo.
echo  [BF1999] SEARCHING FOR HEARTS OF IRON IV...
set "GAME_EXE="
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='SilentlyContinue'; $roots=@(); $s=(Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam').InstallPath; if(!$s){$s=(Get-ItemProperty 'HKCU:\Software\Valve\Steam').SteamPath}; if($s){$roots+= $s; $vf=Join-Path $s 'steamapps\libraryfolders.vdf'; if(Test-Path $vf){$txt=Get-Content $vf -Raw; [regex]::Matches($txt,'(?m)\"path\"\s+\"([^\"]+)\"') | ForEach-Object {$roots+= $_.Groups[1].Value -replace '\\\\','\'}}}; $roots+=@('C:\Program Files (x86)\Steam','C:\Program Files\Steam','D:\Steam','D:\Games\Steam'); $roots=$roots|Select-Object -Unique; foreach($r in $roots){$p=Join-Path $r 'steamapps\common\Hearts of Iron IV\hoi4.exe'; if(Test-Path $p){$p; exit 0}}; exit 1" >"%WORK%\gamepath.txt"
if exist "%WORK%\gamepath.txt" set /p "GAME_EXE="<"%WORK%\gamepath.txt"
if not defined GAME_EXE (
 echo [ERROR] hoi4.exe was not found in common Steam libraries.
 echo [INFO] Add your Steam library to Steam's libraryfolders.vdf or install HOI4 through Steam.
 exit /b 1
)
for %%G in ("%GAME_EXE%") do set "GAME_DIR=%%~dpG"
exit /b 0

:DIAG
cls
echo.
echo  ========================== BF1999 SYSTEM DIAGNOSTICS ==========================
echo.
if exist "%MODSRC%\descriptor.mod" (echo  [OK] Mod package folder detected.) else (echo  [ERROR] Mod package folder missing.)
if exist "%MODSRC%\common\bookmarks\BF1999_bookmark.txt" (echo  [OK] 1999 bookmark file detected.) else (echo  [ERROR] Bookmark missing.)
if exist "%MODSRC%\common\country_tags\zzzz_bf1999_countries.txt" (echo  [OK] Custom country tags detected.) else (echo  [ERROR] Country tag file missing.)
if exist "%MOD_DESC%" (echo  [OK] Installed local descriptor exists.) else (echo  [INFO] Mod has not been installed yet.)
echo.
echo  NOTE: Diagnostics checks files and paths only. It does not prove that the game
echo        will pass the campaign-load stage. This build targets HOI4 1.20.x.
echo.
echo  ================================================================================
pause
goto MENU

:OPEN_MOD
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('MyDocuments')" 2^>nul`) do set "DOCS=%%P"
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
echo.
echo  [BF1999] COMMAND SESSION CLOSED.
call :wait 1
exit /b

:wait
ping 127.0.0.1 -n %~1 -w 1000 >nul
exit /b
