@echo off
cd /d "%~dp0"
echo ====================================================
echo  Generare executabil portabil Voice2Text (Windows 10/11)
echo ====================================================
echo.
if exist "%~dp0.venv\Scripts\python.exe" (
    set "VOICE2TEXT_PYTHON=%~dp0.venv\Scripts\python.exe"
) else (
    set "VOICE2TEXT_PYTHON=python.exe"
)
"%VOICE2TEXT_PYTHON%" "%~dp0build_portable.py"
if errorlevel 1 (
    echo EROARE: Generarea a esuat. Instaleaza dependintele din requirements-dev.txt.
    pause
    exit /b 1
)
echo.
echo ====================================================
echo  Gata! Executabilul se afla in:
echo  %~dp0Voice2Text.exe
echo.
echo  Pastreaza folderele _internal si models langa executabil.
echo ====================================================
pause
