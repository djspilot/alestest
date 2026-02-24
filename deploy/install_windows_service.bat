@echo off
REM ========================================================================
REM ALES Manufacturing Pipeline - Windows Service Installer
REM ========================================================================
REM
REM This script installs the STEP file watcher as a Windows service using NSSM
REM (Non-Sucking Service Manager).
REM
REM Prerequisites:
REM   1. Python 3.8+ installed
REM   2. FreeCAD installed (for unfold functionality)
REM   3. NSSM downloaded (https://nssm.cc/download)
REM
REM Usage:
REM   install_windows_service.bat
REM
REM ========================================================================

echo.
echo ========================================================================
echo ALES Manufacturing Pipeline - Windows Service Installer
echo ========================================================================
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script must be run as Administrator!
    echo Right-click the script and select "Run as administrator"
    pause
    exit /b 1
)

REM Navigate to project directory
cd /d "%~dp0"
echo Working directory: %CD%
echo.

REM Step 1: Check Python installation
echo [1/7] Checking Python installation...
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Python not found. Please install Python 3.8 or higher.
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

python --version
echo Python OK
echo.

REM Step 2: Check/create virtual environment
echo [2/7] Checking virtual environment...
if exist venv\ (
    echo Virtual environment exists
) else (
    echo Creating virtual environment...
    python -m venv venv
    if %errorLevel% neq 0 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo Virtual environment created
)
echo.

REM Step 3: Activate virtual environment and install dependencies
echo [3/7] Installing Python dependencies...
call venv\Scripts\activate.bat
if %errorLevel% neq 0 (
    echo ERROR: Failed to activate virtual environment
    pause
    exit /b 1
)

REM Install main requirements
echo Installing main requirements...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

REM Install watcher-specific requirements
echo Installing watcher requirements...
python -m pip install watchdog python-dotenv

echo Dependencies installed
echo.

REM Step 4: Check FreeCAD installation
echo [4/7] Checking FreeCAD installation...
if exist "C:\Program Files\FreeCAD 0.21\bin\FreeCAD.exe" (
    echo FreeCAD found: C:\Program Files\FreeCAD 0.21\
) else if exist "C:\Program Files\FreeCAD 1.0\bin\FreeCAD.exe" (
    echo FreeCAD found: C:\Program Files\FreeCAD 1.0\
) else (
    echo WARNING: FreeCAD not found in standard location
    echo FreeCAD is required for sheet metal unfold functionality
    echo Download from: https://www.freecad.org/downloads.php
    echo.
    echo Continue anyway? (Y/N)
    choice /c YN /n
    if errorlevel 2 exit /b 1
)
echo.

REM Step 5: Create/verify .env configuration
echo [5/7] Checking configuration...
if not exist .env (
    echo Creating .env from template...
    copy .env.example .env
    echo.
    echo IMPORTANT: Please edit .env and configure:
    echo   - WATCHED_FOLDER (e.g., G:\ALES\Offerte-ALES)
    echo   - LOG_LEVEL (INFO recommended)
    echo.
    echo Press any key after you've configured .env...
    pause
)

echo Configuration:
type .env
echo.

REM Step 6: Check/download NSSM
echo [6/7] Checking NSSM (Service Manager)...
if exist nssm.exe (
    echo NSSM found: %CD%\nssm.exe
) else (
    echo NSSM not found. Downloading...
    echo.
    echo Please download NSSM manually:
    echo 1. Go to: https://nssm.cc/download
    echo 2. Download the latest version
    echo 3. Extract nssm.exe (64-bit) to: %CD%
    echo 4. Re-run this installer
    echo.
    pause
    exit /b 1
)
echo.

REM Step 7: Install as Windows service
echo [7/7] Installing Windows service...

set PYTHON_EXE=%CD%\venv\Scripts\python.exe
set SCRIPT_PATH=%CD%\file_watcher_service.py

echo Python executable: %PYTHON_EXE%
echo Script path: %SCRIPT_PATH%
echo.

REM Remove existing service if present
nssm.exe stop ManufacturingWatcher >nul 2>&1
nssm.exe remove ManufacturingWatcher confirm >nul 2>&1

REM Install service
echo Installing service...
nssm.exe install ManufacturingWatcher "%PYTHON_EXE%" "%SCRIPT_PATH%"
if %errorLevel% neq 0 (
    echo ERROR: Failed to install service
    pause
    exit /b 1
)

REM Configure service
echo Configuring service...
nssm.exe set ManufacturingWatcher AppDirectory "%CD%"
nssm.exe set ManufacturingWatcher DisplayName "ALES Manufacturing Pipeline Watcher"
nssm.exe set ManufacturingWatcher Description "Monitors folders for STEP files and generates manufacturing analysis XML"
nssm.exe set ManufacturingWatcher Start SERVICE_AUTO_START
nssm.exe set ManufacturingWatcher AppStdout "%CD%\logs\service_stdout.log"
nssm.exe set ManufacturingWatcher AppStderr "%CD%\logs\service_stderr.log"

REM Create logs directory
if not exist logs\ mkdir logs

echo Service installed successfully!
echo.

REM Ask to start service
echo Do you want to start the service now? (Y/N)
choice /c YN /n
if errorlevel 2 (
    echo.
    echo Service installed but not started.
    echo To start manually: net start ManufacturingWatcher
    goto :end
)

REM Start service
echo Starting service...
nssm.exe start ManufacturingWatcher
if %errorLevel% neq 0 (
    echo ERROR: Failed to start service
    echo Check logs in: %CD%\logs\
    pause
    exit /b 1
)

echo.
echo Service started successfully!
echo.

:end
echo ========================================================================
echo Installation complete!
echo ========================================================================
echo.
echo Service name: ManufacturingWatcher
echo Service status: Run "nssm.exe status ManufacturingWatcher"
echo.
echo Logs:
echo   - Application: %CD%\file_watcher_service.log
echo   - Service stdout: %CD%\logs\service_stdout.log
echo  - Service stderr: %CD%\logs\service_stderr.log
echo.
echo Service control:
echo   - Start: net start ManufacturingWatcher
echo   - Stop: net stop ManufacturingWatcher
echo   - Restart: net stop ManufacturingWatcher && net start ManufacturingWatcher
echo   - Uninstall: nssm.exe remove ManufacturingWatcher confirm
echo.
echo Watched folder: Check .env file
echo.
pause
