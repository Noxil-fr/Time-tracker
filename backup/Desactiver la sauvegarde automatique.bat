@echo off
rem Retire la sauvegarde planifiee de Time Tracker.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0backup.ps1" -Uninstall
pause
