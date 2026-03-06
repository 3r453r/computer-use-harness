
# Computer-Use Harness - Setup Script
# Usage: . .\setup.ps1
# (dot-source so the venv stays activated in your shell)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Setting up computer-use-harness..." -ForegroundColor Cyan

# 1. Create venv if missing
$venvPath = Join-Path $repoRoot '.venv'
if (-not (Test-Path $venvPath)) {
    Write-Host "Creating Python venv..." -ForegroundColor Yellow
    python -m venv $venvPath
}

# 2. Activate venv
$activateScript = Join-Path $venvPath 'Scripts\Activate.ps1'
Write-Host "Activating venv..." -ForegroundColor Yellow
. $activateScript

# 3. Install package
Write-Host "Installing harness package..." -ForegroundColor Yellow
pip install -q -e $repoRoot

# 4. Create .env from example if missing
$envFile = Join-Path $repoRoot '.env'
$envExample = Join-Path $repoRoot '.env.example'
if (-not (Test-Path $envFile)) {
    Write-Host "Creating .env from .env.example..." -ForegroundColor Yellow
    Copy-Item $envExample $envFile
    Write-Host "IMPORTANT: Set OPENAI_API_KEY in $envFile" -ForegroundColor Red
} else {
    Write-Host ".env already exists, skipping." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""

# Show help so the user knows what's available
computer-use-harness help
