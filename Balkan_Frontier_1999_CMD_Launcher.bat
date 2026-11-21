@echo off
setlocal EnableExtensions
chcp 65001 >nul
title BALKAN FRONTIER 1999 - DIRECT LAUNCHER v0.1.7
color 0B
mode con: cols=100 lines=34 >nul 2>&1
set "ROOT=%~dp0"
set "MODSRC=%ROOT%Balkan_Frontier_1999"
set "DOCS=%USERPROFILE%\Documents"
set "MODROOT=%DOCS%\Paradox Interactive\Hearts of Iron IV\mod"
set "MODDEST=%MODROOT%\Balkan_Frontier_1999"
set "MOD_DESC=%MODROOT%\Balkan_Frontier_1999.mod"
set "GAME_EXE="

:MENU
cls
echo.
echo  ====================================================================================================
echo       B A L K A N   F R O N T I E R   1 9 9 9
echo                         DIRECT COMMAND CENTER // BUILD 0.1.7
echo  ====================================================================================================
echo.
echo       [1] INSTALL MOD AND START HOI4
echo       [2] INSTALL MOD ONLY
echo       [3] CHECK FILES AND PATHS
echo       [0] EXIT
echo.
set "CHOICE="
set /p "CHOICE=  BF1999@COMMAND> "
if "%CHOICE%"=="1" goto INSTALL_AND_START
if "%CHOICE%"=="2" goto INSTALL_ONLY
if "%CHOICE%"=="3" goto DIAGNOSTICS
if "%CHOICE%"=="0" goto EXIT
goto MENU

:RESOLVE_MOD
if exist "%MODSRC%\descriptor.mod" exit /b 0
echo.
echo [ERROR] Folder Balkan_Frontier_1999 is not beside this BAT.
echo [HELP] Paste the full path to the extracted mod folder.
set "MODSRC="
set /p "MODSRC=Mod folder path> "
set "MODSRC=%MODSRC:"=%"
if not exist "%MODSRC%\descriptor.mod" (
 echo [ERROR] descriptor.mod was not found in that folder.
 exit /b 1
)
exit /b 0

:INSTALL_ONLY
call :INSTALL_MOD
if errorlevel 1 goto FAIL
echo [OK] Mod installation finished.
pause
goto MENU

:INSTALL_AND_START
call :INSTALL_MOD
if errorlevel 1 goto FAIL
call :GET_GAME_PATH
if errorlevel 1 goto FAIL
echo [OK] Mod installed.
echo [OK] Game executable: %GAME_EXE%
echo [START] Starting HOI4 directly...
start "Balkan Frontier 1999" "%GAME_EXE%" "-mod=%MOD_DESC%"
echo [INFO] Launch command sent. Paradox Launcher is not opened by this BAT.
pause
goto MENU

:INSTALL_MOD
cls
echo [BF1999] INSTALLING MOD...
call :RESOLVE_MOD
if errorlevel 1 exit /b 1
if not exist "%MODROOT%" md "%MODROOT%" 2>nul
if not exist "%MODROOT%" (
 echo [ERROR] Cannot create mod directory: %MODROOT%
 exit /b 1
)
robocopy "%MODSRC%" "%MODDEST%" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NC /NS /NP >nul
if errorlevel 8 (
 echo [ERROR] Copy failed. Close HOI4 and retry.
 exit /b 1
)
set "MODDEST_FWD=%MODDEST:\=/%"
(
 echo name="Balkan Frontier 1999"
 echo path="%MODDEST_FWD%"
 echo version="0.1.7"
 echo supported_version="1.20.*"
 echo replace_path="history/states"
 echo replace_path="map"
)>"%MOD_DESC%"
if not exist "%MOD_DESC%" (
 echo [ERROR] Could not write descriptor: %MOD_DESC%
 exit /b 1
)
if not exist "%MODDEST%\common\bookmarks\BF1999_bookmark.txt" (
 echo [ERROR] Bookmark file missing after copy.
 exit /b 1
)
if not exist "%MODDEST%\common\country_tags\zzzz_bf1999_countries.txt" (
 echo [ERROR] Country tag file missing after copy.
 exit /b 1
)
echo [OK] Mod installed to %MODDEST%
exit /b 0

:GET_GAME_PATH
cls
echo [BF1999] SEARCHING FOR HEARTS OF IRON IV...
if exist "D:\SteamLibrary\steamapps\common\Hearts of Iron IV\hoi4.exe" (
 set "GAME_EXE=D:\SteamLibrary\steamapps\common\Hearts of Iron IV\hoi4.exe"
)
if defined GAME_EXE exit /b 0
echo.
echo Enter either the game folder OR the full path to hoi4.exe.
echo Example: D:\SteamLibrary\steamapps\common\Hearts of Iron IV
set "GAME_INPUT="
set /p "GAME_INPUT=Game path> "
set "GAME_INPUT=%GAME_INPUT:"=%"
if exist "%GAME_INPUT%\hoi4.exe" set "GAME_EXE=%GAME_INPUT%\hoi4.exe"
if not defined GAME_EXE (
 for %%I in ("%GAME_INPUT%") do if /i "%%~xI"==".exe" set "GAME_EXE=%%~fI"
)
if not defined GAME_EXE (
 echo [ERROR] Input was not a game folder or hoi4.exe.
 exit /b 1
)
if not exist "%GAME_EXE%" (
 echo [ERROR] hoi4.exe not found: %GAME_EXE%
 exit /b 1
)
exit /b 0

:DIAGNOSTICS
cls
echo ======================== BF1999 DIAGNOSTICS v0.1.7 ========================
if exist "%MODSRC%\descriptor.mod" (echo [OK] Mod source folder found.) else (echo [INFO] Mod source folder is not beside BAT.)
if exist "D:\SteamLibrary\steamapps\common\Hearts of Iron IV\hoi4.exe" (echo [OK] HOI4 found in D: SteamLibrary.) else (echo [INFO] HOI4 not found at the known D: path.)
echo.
echo This checks paths only; it does not test the game engine.
pause
goto MENU

:FAIL
echo.
echo [FAILED] Operation stopped. No game process was started.
pause
goto MENU

:EXIT
echo [BF1999] SESSION CLOSED.
exit /b
