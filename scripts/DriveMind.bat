@echo off
rem Opens the DriveMind dashboard at http://127.0.0.1:7878
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\install.ps1 first.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m drivemind tray
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:7878
