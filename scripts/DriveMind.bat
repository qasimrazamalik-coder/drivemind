@echo off
rem Opens the DriveMind dashboard at http://127.0.0.1:7878
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\install.ps1 first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m drivemind serve
