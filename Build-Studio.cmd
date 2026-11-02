@echo off
setlocal EnableExtensions
cd /d "%~dp0"
where node.exe >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js not found. Install Node.js 22 or later.
  pause
  exit /b 1
)
where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm.cmd not found. Repair Node.js installation.
  pause
  exit /b 1
)
echo [1/3] Installing frontend dependencies...
pushd frontend
call npm.cmd install
if errorlevel 1 goto :failed
echo [2/3] Checking TypeScript...
call npm.cmd run check
if errorlevel 1 goto :failed
echo [3/3] Building Visual Studio...
call npm.cmd run build
if errorlevel 1 goto :failed
popd
echo.
echo [OK] Visual Studio built into web\studio.
echo Run Yorimiyu.bat and open the Visual Studio link.
pause
exit /b 0
:failed
set "CODE=%ERRORLEVEL%"
popd
echo [ERROR] Build failed, code %CODE%. The original UI remains unchanged.
pause
exit /b %CODE%
