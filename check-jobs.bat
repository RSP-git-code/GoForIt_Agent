@echo off
rem Scans your LinkedIn/Indeed job alerts now: Gmail -> Excel tracker -> 9 AM calendar reminder.
rem Also use this when the daily scan's log says the Google sign-in expired.
cd /d "%~dp0backend"
echo Checking your job alerts...
echo.
".venv\Scripts\python.exe" -m app.inbox --logged
echo.
echo ============================================================
echo  Done. Read the summary above (it's also saved in
echo  Documents\GoForIt\inbox-log.txt). Press any key to close.
echo ============================================================
pause > nul
