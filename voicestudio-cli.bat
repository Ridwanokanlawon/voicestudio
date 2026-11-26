@echo off
rem Command-line access to the running Voice Studio app. Example:
rem   voicestudio-cli generate --preset "WCGW - Harry" --in script.txt --episode EP22
"%~dp0runtime\Scripts\python.exe" "%~dp0tools\voicestudio_cli.py" %*
