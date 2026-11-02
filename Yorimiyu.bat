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

if not exist "logs" mkdir "logs" 2>nul
set "PY_EXE="
set "PY_ARGS="
set "PY_FOUND=0"

rem Check the portable interpreter, then the Windows launcher, then PATH.
if exist ".runtime\python\python.exe" (
  set "PY_FOUND=1"
  ".runtime\python\python.exe" -c "import sys,sqlite3,ssl;sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
  if not errorlevel 1 (
    set "PY_EXE=%CD%\.runtime\python\python.exe"
    goto start
  )
)
where py.exe >nul 2>&1
if not errorlevel 1 (
  set "PY_FOUND=1"
  py.exe -3 -c "import sys,sqlite3,ssl;sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
  if not errorlevel 1 (
    set "PY_EXE=py.exe"
    set "PY_ARGS=-3"
    goto start
  )
)
where python.exe >nul 2>&1
if not errorlevel 1 (
  set "PY_FOUND=1"
  python.exe -c "import sys,sqlite3,ssl;sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
  if not errorlevel 1 (
    set "PY_EXE=python.exe"
    goto start
  )
)
if "%PY_FOUND%"=="0" goto no_python
goto bad_python

:start
echo [Yorimiyu] Python: %PY_EXE% %PY_ARGS%
echo [Yorimiyu] Project: %CD%
echo [Yorimiyu] Starting local dashboard...
"%PY_EXE%" %PY_ARGS% -u "launcher.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto failed
goto done

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
