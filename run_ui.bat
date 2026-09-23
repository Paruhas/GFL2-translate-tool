@echo off
chcp 65001 >nul
title GFL2 Translation Manager
python "%~dp0app_ui.py"
if %errorlevel% neq 0 (
    echo.
    echo An error occurred while running the GUI.
    pause
)
