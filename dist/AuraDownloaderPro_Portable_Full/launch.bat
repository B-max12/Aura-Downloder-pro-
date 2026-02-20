@echo off
REM Aura Downloader Pro Launcher
REM This script launches the Aura Downloader Pro application

echo Starting Aura Downloader Pro...
echo.

REM Get the directory where this batch file is located
set "APP_DIR=%~dp0"

REM Launch the application
start "" "%APP_DIR%AuraDownloaderPro.exe"

REM Exit the batch file
exit /b