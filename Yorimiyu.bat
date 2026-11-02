@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Yorimiyu - Local Web
pushd "%~dp0" 2>nul
if errorlevel 1 (
  echo [ERROR] Cannot access project directory.
  pause
  exit /b 3
)
set "PY_EXE="
set "PY_ARGS="
if exist ".runtime\python\python.exe" (
  set "PY_EXE=%CD%\.runtime\python\python.exe"
) else (
  where py.exe >nul 2>&1
  if not errorlevel 1 (
    set "PY_EXE=py.exe"
    set "PY_ARGS=-3"
  ) else (
    where python.exe >nul 2>&1
    if not errorlevel 1 set "PY_EXE=python.exe"
  )
)
if not defined PY_EXE goto no_python
"%PY_EXE%" %PY_ARGS% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 goto bad_python
if not exist "launcher.py" goto missing
if not exist "web\index.html" goto missing
"%PY_EXE%" %PY_ARGS% "launcher.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto failed
goto done
:no_python
echo [ERROR] Python 3.10+ was not found. Install Python or put portable python.exe in .runtime\python.
set "RC=2"
goto failed
:bad_python
echo [ERROR] Python runtime is broken or older than 3.10.
set "RC=2"
goto failed
:missing
echo [ERROR] Missing launcher.py or web\index.html. Download the complete repository.
set "RC=2"
goto failed
:failed
echo.
echo Launch failed with exit code %RC%.
pause
:done
popd
endlocal & exit /b %RC%
