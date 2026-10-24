@echo off
rem Starts the GoForIt backend (needed for "Fill this page", Agent Octo and the Applied/Expired links).
rem Keep this window open while you use them; close it when you're done.

rem Agent Octo's chat and the AI drafts need Ollama (the local AI). If it's installed but not
rem running (it doesn't always start after a reboot), start its tray app, which runs it in the background.
tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /I "ollama.exe" >nul
if errorlevel 1 (
  if exist "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe" (
    echo Starting Ollama ^(the local AI^)...
    start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
  ) else (
    echo Ollama isn't installed: Octo's free chat and AI drafts will be off. Everything else works.
  )
)

cd /d "%~dp0backend"
".venv\Scripts\python.exe" -m app.main
