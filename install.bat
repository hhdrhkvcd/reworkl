@echo off
setlocal EnableExtensions DisableDelayedExpansion
call "%~dp0installer\bat\1_INSTALL.bat" %*
set "RESULT=%ERRORLEVEL%"
exit /b %RESULT%
