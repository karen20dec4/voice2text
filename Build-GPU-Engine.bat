@echo off
cd /d "%~dp0"
echo ====================================================
echo  Compilare motor GPU Voice2Text (whisper.cpp + Vulkan)
echo ====================================================
echo.
for /f "usebackq delims=" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath`) do set "VOICE2TEXT_VS=%%i"
call "%VOICE2TEXT_VS%\VC\Auxiliary\Build\vcvars64.bat" >nul
if exist "%~dp0.venv\Scripts\python.exe" (
    set "VOICE2TEXT_PYTHON=%~dp0.venv\Scripts\python.exe"
) else (
    set "VOICE2TEXT_PYTHON=python.exe"
)
"%VOICE2TEXT_PYTHON%" "%~dp0build_gpu_engine.py"
if errorlevel 1 (
    echo EROARE: Compilarea a esuat. Verifica Visual Studio Build Tools si Git.
    if "%~1"=="" pause
    exit /b 1
)
echo.
echo Gata! Pastreaza folderul gpu langa executabil.
if "%~1"=="" pause
