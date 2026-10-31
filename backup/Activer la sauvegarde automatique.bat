@echo off
rem Planifie la sauvegarde de Time Tracker : tous les jours a 20h et a l'ouverture de session.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0backup.ps1" -Install
pause
