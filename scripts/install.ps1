# DriveMind installer for Windows (no admin needed).
# Run from the project folder:  powershell -ExecutionPolicy Bypass -File scripts\install.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
if (-not $py) { Write-Host "Install Python 3.10+ from https://www.python.org/downloads/ first." -ForegroundColor Red; exit 1 }

Write-Host "Creating virtual environment..." -ForegroundColor Cyan
& $py.Source -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\.venv\Scripts\python.exe -m pip install -e ".[watch]" --quiet

Write-Host "Adding the Explorer right-click menu..." -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m drivemind shell install

$ans = Read-Host "Start DriveMind with Windows (background guardian, no window)? [y/N]"
if ($ans -match '^[yY]') { & .\.venv\Scripts\python.exe -m drivemind shell autostart-on }

Write-Host "`nDone. Open the dashboard with:  scripts\DriveMind.bat" -ForegroundColor Green
Write-Host "Optional local AI: install Ollama (https://ollama.com) then run:  ollama pull qwen3:4b"
