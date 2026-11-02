@echo off
setlocal
cd /d "%~dp0"
title Yorimiyu - Local Web
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo Python 3 not found. Install Python from python.org
  pause
  exit /b 1
)
%PY% -c "import sys; assert sys.version_info >= (3,10), 'Python 3.10+ required'" || (pause & exit /b 1)
%PY% launcher.py
if errorlevel 1 pause
