@echo off
setlocal
title Build Time Tracker Installer
echo.
echo  =========================================
echo   Time Tracker — Build complet
echo  =========================================
echo.

:: ── 1. PyInstaller ──────────────────────────────────────────────────────────
echo [1/2] Construction de l'executable (PyInstaller)...
python -m PyInstaller --clean --noconfirm TimeTracker.spec
if errorlevel 1 (
    echo.
    echo  ERREUR : PyInstaller a echoue.
    pause & exit /b 1
)
echo  OK - dist\TimeTracker\TimeTracker.exe cree.
echo.

:: ── 2. Inno Setup ───────────────────────────────────────────────────────────
echo [2/2] Compilation de l'installeur (Inno Setup)...

set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
    set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
)

if not defined ISCC (
    echo.
    echo  ERREUR : Inno Setup 6 introuvable.
    echo  Telechargez-le sur : https://jrsoftware.org/isinfo.php
    pause & exit /b 1
)

%ISCC% installer\TimeTracker.iss
if errorlevel 1 (
    echo.
    echo  ERREUR : Inno Setup a echoue.
    pause & exit /b 1
)

echo.
echo  =========================================
echo   Termine !
echo   installer\Output\TimeTracker_Setup_v1.0.exe
echo  =========================================
echo.
pause
