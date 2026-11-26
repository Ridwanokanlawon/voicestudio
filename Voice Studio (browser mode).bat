@echo off
rem Troubleshooting: runs Voice Studio with a console window and a browser tab instead of its own window.
title Voice Studio (close this window to stop)
cd /d "%~dp0"
"runtime\Scripts\python.exe" -m app.server
pause
