@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Yorimiyu - Local Web
pushd "%~dp0" 2>nul
if errorlevel 1 (
  echo [ERROR] Cannot access the project folder.
  pause
  exit /b 3
)
if not exist "launcher.py" goto missing
if not exist "web\index.html" goto missing
if not exist "ai_workspace.py" goto missing
if not exist "memory_bridge.py" goto missing
if not exist "graphiti_adapter.py" goto missing
if not exist "graphiti_delivery.py" goto missing
if not exist "web\app.js" goto missing
if not exist "install-python.ps1" goto missing

if not exist "logs" mkdir "logs" 2>nul
set "PY_EXE="
set "PY_ARGS="

rem Always prefer the project-owned interpreter. Windows Python aliases can be broken.
if exist ".runtime\python\python.exe" (
  ".runtime\python\python.exe" -c "import sys,sqlite3,ssl,os,memory_bridge;sys.exit(0 if sys.version_info >= (3,10) and os.path.isfile(sys.executable) else 1)" >nul 2>&1
  if not errorlevel 1 (
    set "PY_EXE=.runtime\python\python.exe"
    goto start
  )
)
goto install_python

:start
echo [Yorimiyu] Python: %PY_EXE% %PY_ARGS%
echo [Yorimiyu] Starting local dashboard...
"%PY_EXE%" %PY_ARGS% -u "launcher.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto failed
echo.
echo [Yorimiyu] Launcher has stopped normally.
echo [INFO] If the browser did not open, check the URL printed above.
echo [INFO] This window will remain open so you can read the status.
pause
goto done

:install_python
echo [Yorimiyu] Preparing a project-owned Python runtime (ignoring broken system aliases)...
where powershell.exe >nul 2>&1
if errorlevel 1 goto no_powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "install-python.ps1"
if errorlevel 1 goto python_install_failed
if not exist ".runtime\python\\python.exe" goto python_install_failed
".runtime\python\\python.exe" -c "import sys,sqlite3,ssl;sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 goto python_install_failed
set "PY_EXE=.runtime\python\\python.exe"
set "PY_ARGS="
goto start

:no_powershell
echo [ERROR] Windows PowerShell is required for automatic Python setup.
set "RC=2"
goto failed

:python_install_failed
echo [ERROR] Automatic Python setup failed. Check .runtime\python-install.log
echo [INFO] Internet access to www.python.org is required for first setup.
set "RC=2"
goto failed

:no_python
echo [ERROR] Python 3.10+ was not found.
echo Install Python from python.org or place a working interpreter in .runtime\python.
set "RC=2"
goto failed

:bad_python
echo [ERROR] Python was found but is too old or cannot load sqlite3 and ssl.
echo Try: py -3 --version
echo Try: python --version
echo Reinstall Python 3.10+ with the standard library.
set "RC=2"
goto failed

:missing
echo [ERROR] Project files are missing. Download the complete Yorimiyu repository.
set "RC=2"
goto failed

:failed
echo.
echo [ERROR] Yorimiyu exited with code %RC%.
echo [INFO] Check logs\launch.log for the Python traceback.
echo [INFO] Run Yorimiyu.bat from a Command Prompt to preserve the full error.
pause

:done
popd
endlocal & exit /b %RC%
