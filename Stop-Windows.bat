@echo off
cd /d "%~dp0"
title CreditProbe Deal Desk - stopping
echo  Stopping CreditProbe Deal Desk (your uploads and work are kept) ...
docker compose stop
echo  Stopped. Start it again with Start-Windows.bat.
pause
