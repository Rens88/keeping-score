@echo off
setlocal EnableExtensions

title Weekend Tournament Tracker LAN Launcher

set "FAIL_STEP="
set "APP_EXIT=0"
set "EXIT_CODE=0"
set "DID_PUSHD=0"
set "SCRIPT=%~f0"
set "SCRIPT_DIR=%~dp0"

echo ============================================================
echo Weekend Tournament Tracker LAN launcher
echo Script : "%SCRIPT%"
echo Folder : "%SCRIPT_DIR%"
echo Started: %DATE% %TIME%
echo ============================================================
echo.

echo [STEP] Change directory to project root...
pushd "%SCRIPT_DIR%\.."
if errorlevel 1 (
    set "FAIL_STEP=cd_project_root"
    goto :fail
)
set "DID_PUSHD=1"
echo [OK] Working directory: "%CD%"
echo.

echo [STEP] Resolve host/port...
if "%STREAMLIT_SERVER_ADDRESS%"=="" (
    set "STREAMLIT_SERVER_ADDRESS=0.0.0.0"
    echo [INFO] STREAMLIT_SERVER_ADDRESS not set. Using default: %STREAMLIT_SERVER_ADDRESS%
) else (
    echo [INFO] STREAMLIT_SERVER_ADDRESS=%STREAMLIT_SERVER_ADDRESS%
)
if "%STREAMLIT_SERVER_PORT%"=="" (
    set "STREAMLIT_SERVER_PORT=8501"
    echo [INFO] STREAMLIT_SERVER_PORT not set. Using default: %STREAMLIT_SERVER_PORT%
) else (
    echo [INFO] STREAMLIT_SERVER_PORT=%STREAMLIT_SERVER_PORT%
)
echo.

echo [STEP] Detect Python interpreter...
set "PYTHON="
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
    echo [OK] Using project venv interpreter: ".venv\Scripts\python.exe"
) else (
    echo [INFO] No local .venv interpreter found. Looking for Python on PATH...
    where python >nul 2>&1
    if errorlevel 1 (
        set "FAIL_STEP=detect_python"
        echo [ERROR] Python was not found on PATH.
        goto :fail
    )
    set "PYTHON=python"
    echo [OK] Using Python from PATH.
)
%PYTHON% --version
if errorlevel 1 (
    set "FAIL_STEP=python_version"
    goto :fail
)
echo.

echo [STEP] Verify Streamlit is available...
%PYTHON% -c "import streamlit as st; print('[DEBUG] streamlit :', st.__version__)"
if errorlevel 1 (
    set "FAIL_STEP=streamlit_import"
    echo [ERROR] Streamlit is not available in the selected Python environment.
    echo [INFO] Install dependencies with: pip install -r requirements.txt
    goto :fail
)
echo.

echo [STEP] Start app in LAN mode...
echo [INFO] Command:
echo        %PYTHON% -m streamlit run app.py --server.address %STREAMLIT_SERVER_ADDRESS% --server.port %STREAMLIT_SERVER_PORT%
%PYTHON% -m streamlit run app.py --server.address %STREAMLIT_SERVER_ADDRESS% --server.port %STREAMLIT_SERVER_PORT%
set "APP_EXIT=%errorlevel%"
echo.
echo [INFO] Streamlit process exited with code: %APP_EXIT%

if not "%APP_EXIT%"=="0" (
    set "FAIL_STEP=run_streamlit"
    goto :fail_with_code
)

echo [OK] Launcher finished without reported errors.
goto :success

:fail_with_code
set "EXIT_CODE=%APP_EXIT%"
echo [ERROR] Step "%FAIL_STEP%" failed with exit code %APP_EXIT%.
goto :final

:fail
if "%EXIT_CODE%"=="0" set "EXIT_CODE=1"
echo [ERROR] Step "%FAIL_STEP%" failed.
echo.
echo Troubleshooting tips:
echo  1. Ensure Python 3 is installed and available on PATH.
echo  2. Run: pip install -r requirements.txt
echo  3. If needed, set STREAMLIT_SERVER_PORT to a free port.
goto :final

:success
set "EXIT_CODE=0"
goto :final

:final
if "%DID_PUSHD%"=="1" popd >nul 2>&1
echo.
echo Finished: %DATE% %TIME%
echo Press any key to close this window...
pause >nul

endlocal & exit /b %EXIT_CODE%
