@echo off
title AutoGrader
echo Starting AutoGrader in Ubuntu. Keep this window open while using the app.
echo Open http://127.0.0.1:7860 when the server is ready.
wsl.exe -d Ubuntu --cd "%~dp0." -- bash ./run-local.sh %*
if errorlevel 1 (
    echo.
    echo Startup failed. If Ubuntu setup is incomplete, open Ubuntu and finish setup first.
    pause
)
