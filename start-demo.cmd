@echo off
rem One-click local demo for Windows: no Docker, no database, no API keys.
rem Starts the labelled demo UI, waits until it answers, opens the browser.
setlocal
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js 20 or newer is required: https://nodejs.org/
  pause
  exit /b 1
)

node "scripts\local\demo.mjs" %*
if errorlevel 1 pause
