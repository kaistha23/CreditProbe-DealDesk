@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title CreditProbe Deal Desk - starting

echo.
echo  CreditProbe AI - Deal Desk edition
echo  ----------------------------------
echo.

where docker >nul 2>nul
if errorlevel 1 (
  echo  Docker Desktop is not installed.
  echo  Install it from https://www.docker.com/products/docker-desktop/ , restart the PC,
  echo  open Docker Desktop once, then double-click this file again.
  start "" "https://www.docker.com/products/docker-desktop/"
  pause
  exit /b 1
)

docker info >nul 2>nul
if not errorlevel 1 goto dockerok
echo  Starting Docker Desktop ...
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
set /a tries=0
:waitdocker
timeout /t 5 /nobreak >nul
docker info >nul 2>nul
if not errorlevel 1 goto dockerok
set /a tries+=1
if %tries% LSS 60 goto waitdocker
echo  Docker Desktop did not start. Open it from the Start menu, wait for "Engine running", then run this file again.
pause
exit /b 1
:dockerok

if not exist "settings.env" (
  copy /y "settings.env.example" "settings.env" >nul
  echo  First run: Notepad opens settings.env.
  echo  Paste your Anthropic API key after ANTHROPIC_API_KEY= , save, and close Notepad.
  echo  No key? Just close Notepad: the app still runs, without the AI drafting and chat.
  notepad "settings.env"
)

echo  Building and starting. The FIRST run downloads and builds everything: 10-20 minutes.
echo  Later starts take about a minute.
echo.
docker compose up -d --build
if errorlevel 1 (
  echo.
  echo  The build or start failed. See the messages above.
  pause
  exit /b 1
)

echo.
echo  Waiting for CreditProbe to finish preparing its data (first start: 3-10 minutes) ...
set /a n=0
:waitapp
curl -fs -o nul http://127.0.0.1:8508/api/v1/dealdesk/desk/health >nul 2>nul && curl -fs -o nul http://127.0.0.1:6600/login >nul 2>nul && goto ready
set /a n+=1
if %n% GEQ 240 goto slow
timeout /t 5 /nobreak >nul
goto waitapp

:slow
echo  It is taking longer than expected. Recent log lines:
docker compose logs --tail 40
echo  Open http://127.0.0.1:6600 in a few minutes, or run Stop-Windows.bat and then Start-Windows.bat.
pause
exit /b 1

:ready
echo.
echo  READY:  http://127.0.0.1:6600
echo  Sign in as  nawaf.alotaibi  (password nawaf.alotaibi)  - Relationship Manager
echo        or  sara.aldosari   (password sara.aldosari)   - Credit Analyst
echo.
start "" "http://127.0.0.1:6600"
echo  You can close this window. CreditProbe keeps running until you run Stop-Windows.bat.
pause
