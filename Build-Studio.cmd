@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" 2>nul
if errorlevel 1 exit /b 3
if not exist "logs" mkdir "logs" >nul 2>&1
if not exist "frontend\package.json" goto missing
if not exist "web" goto missing

rem Node.js is required only for building React Studio, not the Python dashboard.
where node.exe >nul 2>&1
if errorlevel 1 goto install_node
where npm.cmd >nul 2>&1
if errorlevel 1 goto install_node
goto check_node

:install_node
echo [Yorimiyu] Node.js not found. Trying automatic installation with winget...
where winget.exe >nul 2>&1
if errorlevel 1 goto node_missing
winget.exe install --id OpenJS.NodeJS.LTS --exact --source winget --accept-source-agreements --accept-package-agreements --silent --disable-interactivity
if errorlevel 1 goto node_missing
rem The current process does not inherit PATH changes made by the installer.
if exist "%ProgramFiles%\nodejs\node.exe" set "PATH=%ProgramFiles%\nodejs;%PATH%"
if exist "%APPDATA%\npm\npm.cmd" set "PATH=%APPDATA%\npm;%PATH%"
where node.exe >nul 2>&1
if errorlevel 1 goto node_missing
where npm.cmd >nul 2>&1
if errorlevel 1 goto node_missing

:check_node
node.exe -e "process.exit(Number(process.versions.node.split('.')[0])>=22?0:1)" >nul 2>&1
if errorlevel 1 goto node_old
if exist "frontend\node_modules\.yorimiyu-package.json" if exist "web\studio\index.html" (
  fc /b "frontend\package.json" "frontend\node_modules\.yorimiyu-package.json" >nul 2>&1
  if not errorlevel 1 (
    powershell.exe -NoProfile -NonInteractive -Command "$out=(Get-Item 'web/studio/index.html').LastWriteTimeUtc; $files=Get-ChildItem 'frontend/src' -File -Recurse; $files+=Get-Item 'frontend/vite.config.ts'; if(@($files | Where-Object {$_.LastWriteTimeUtc -gt $out}).Count -eq 0){exit 0}else{exit 1}" >nul 2>&1
    if not errorlevel 1 (
      echo [Yorimiyu] Visual Studio dependencies and bundle are already prepared.
      goto success
    )
  )
)
echo [Yorimiyu] Installing and checking React Visual Studio...
pushd "frontend"
call npm.cmd install --no-audit --no-fund --prefer-offline
if errorlevel 1 goto build_failed
call npm.cmd run check
if errorlevel 1 goto build_failed
call npm.cmd run build
if errorlevel 1 goto build_failed
copy /y "package.json" "node_modules\.yorimiyu-package.json" >nul
popd
echo [Yorimiyu] React Studio installed and built.
goto success

:build_failed
set "CODE=%ERRORLEVEL%"
popd
echo [WARN] React Studio setup failed with code %CODE%. The original dashboard can still start.
echo [INFO] Run Build-Studio.cmd again after checking the npm error above.
goto failed

:node_old
echo [WARN] Node.js 22+ is required for Visual Studio. Update Node.js LTS.
goto failed

:node_missing
echo [WARN] Node.js could not be installed automatically.
echo [INFO] Install Node.js LTS from https://nodejs.org/ and start Yorimiyu.bat again.
goto failed

:missing
echo [WARN] React Studio source files are missing.
goto failed

:success
popd
endlocal & exit /b 0
:failed
popd
endlocal & exit /b 1
