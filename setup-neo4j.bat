@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" || (pause & exit /b 1)
echo [Yorimiyu] Local Neo4j setup
echo Docker Desktop may require administrator approval and WSL2 setup.
echo.
choice /c YN /m "Allow Docker Desktop installation if it is missing"
if errorlevel 2 (
  set "YORIMIYU_INSTALL_DOCKER=0"
) else (
  set "YORIMIYU_INSTALL_DOCKER=1"
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "start-neo4j.ps1"
echo.
echo Setup log: .runtime\neo4j-setup.log
pause
popd
