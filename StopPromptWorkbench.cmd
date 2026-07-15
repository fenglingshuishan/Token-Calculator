@echo off
setlocal
title Stop Prompt Cost Workbench

wsl.exe -d Ubuntu -- bash -lc "cd /home/hcj/dev/token-calculator && ./stop.sh"
if errorlevel 1 (
  echo.
  echo Prompt Workbench could not be stopped.
  pause
  exit /b 1
)

echo.
echo Prompt Workbench has stopped. You may close this window.
timeout /t 2 /nobreak >nul
exit /b 0
