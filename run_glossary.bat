@echo off
chcp 65001 >nul
:menu
cls
echo =================================================================
echo         GFL2 LORE GLOSSARY MANAGER (DATABASE-DRIVEN)
echo =================================================================
echo   1. Audit ^& Auto-Fix Mistranslations (Database ^& translations_eng.json)
echo   2. View all Glossary Terms in Database
echo   3. Export Glossary to glossary.json
echo   4. Import Glossary from glossary.json
echo   5. Exit
echo =================================================================
set /p choice=Select an option (1-5): 

if "%choice%"=="1" (
    echo.
    python "%~dp0apply_glossary.py" fix
    pause
    goto menu
)
if "%choice%"=="2" (
    echo.
    python "%~dp0apply_glossary.py" list
    pause
    goto menu
)
if "%choice%"=="3" (
    echo.
    python "%~dp0apply_glossary.py" export
    pause
    goto menu
)
if "%choice%"=="4" (
    echo.
    python "%~dp0apply_glossary.py" import
    pause
    goto menu
)
if "%choice%"=="5" (
    exit /b
)
goto menu
