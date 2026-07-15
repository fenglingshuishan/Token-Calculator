@echo off
setlocal
title Prompt Cost Workbench Launcher

wsl.exe -d Ubuntu -- bash -lc "cd /home/hcj/dev/token-calculator && PROMPT_WORKBENCH_NO_OPEN=1 ./start.sh"
if errorlevel 1 (
  echo.
  echo Prompt Workbench failed to start.
  echo Log: \\wsl.localhost\Ubuntu\home\hcj\dev\token-calculator\server.log
  pause
  exit /b 1
)

start "" "http://127.0.0.1:8000"
exit /b 0
