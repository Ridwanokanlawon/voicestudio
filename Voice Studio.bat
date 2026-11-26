@echo off
rem Starts Voice Studio in its own window. If the app has not been set up yet, runs Setup first.
cd /d "%~dp0"
if exist "runtime\Scripts\pythonw.exe" goto run
title Voice Studio setup
echo First start: Voice Studio needs to set itself up.
call "%~dp0Setup.bat" -Engines none -Yes
if errorlevel 1 (
  echo.
  echo Setup did not finish. See the messages above.
  pause
  exit /b 1
)
:run
start "" "runtime\Scripts\pythonw.exe" -m app.desktop
