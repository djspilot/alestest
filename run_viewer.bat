@echo off
setlocal

cd /d "%~dp0"

set "NODEJS_DIR=C:\Program Files\nodejs"
if exist "%NODEJS_DIR%\node.exe" (
  set "PATH=%NODEJS_DIR%;%PATH%"
)

set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if not exist "%PYTHON_EXE%" (
  where python >nul 2>nul
  if %ERRORLEVEL%==0 (
    set "PYTHON_EXE=python"
  ) else (
    echo Python was not found. Install Python or update PYTHON_EXE in run_viewer.bat.
    exit /b 1
  )
)

"%PYTHON_EXE%" run_viewer.py %*
exit /b %ERRORLEVEL%
