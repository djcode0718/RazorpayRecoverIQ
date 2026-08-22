param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [string]$ServerHost = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

if (-not (Get-Command $pythonExe -ErrorAction SilentlyContinue)) {
    throw "Python is not available. Create .venv or install Python and retry."
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is not available. Install Node.js and retry."
}

if (-not (Test-Path (Join-Path $repoRoot "frontend\node_modules"))) {
    Write-Host "Installing frontend dependencies..."
    Push-Location (Join-Path $repoRoot "frontend")
    npm install
    Pop-Location
}

$env:PYTHONPATH = Join-Path $repoRoot "backend"

$backendArgs = @("-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", $ServerHost, "--port", "$BackendPort")
$frontendArgs = @("run", "dev", "--", "--host", $ServerHost, "--port", "$FrontendPort")

$backendProc = Start-Process -FilePath $pythonExe -ArgumentList $backendArgs -WorkingDirectory $repoRoot -PassThru -NoNewWindow
$frontendProc = Start-Process -FilePath "npm.cmd" -ArgumentList $frontendArgs -WorkingDirectory (Join-Path $repoRoot "frontend") -PassThru -NoNewWindow

Write-Host "RecoverIQ is starting..."
Write-Host "Backend : http://$ServerHost`:$BackendPort"
Write-Host "Frontend: http://$ServerHost`:$FrontendPort"
Write-Host "Press Ctrl+C to stop both processes."

try {
    while ($true) {
        Start-Sleep -Seconds 1
        if ($backendProc.HasExited -or $frontendProc.HasExited) {
            break
        }
    }
}
finally {
    foreach ($proc in @($backendProc, $frontendProc)) {
        if ($null -ne $proc -and -not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force
        }
    }
}
