@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make_share_zip.ps1" %*
pause
