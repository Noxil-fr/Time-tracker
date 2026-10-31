@echo off
rem Sauvegarde manuelle de Time Tracker : zip du dossier data, copie sur D: et E: (30 dernieres gardees).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0backup.ps1"
pause
