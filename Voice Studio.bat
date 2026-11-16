@echo off
title Voice Studio (close this window to stop)
cd /d "%~dp0"
if exist "runtime\Scripts\python.exe" goto run
echo First start: Voice Studio needs to set itself up.
call "%~dp0Setup.bat"
if errorlevel 1 (
  echo.
  echo Setup did not finish. See the messages above.
  pause
  exit /b 1
)
:run
"runtime\Scripts\python.exe" -m app.server
if errorlevel 1 pause
