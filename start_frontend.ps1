$projectRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$frontendDir = Join-Path $projectRoot 'web/frontend'
if (-not (Test-Path (Join-Path $frontendDir 'package.json'))) {
    throw 'Open PowerShell in the SecureFed-IDS project folder and run .\start_frontend.ps1.'
}
$uiPort = if ($env:SECUREFED_UI_PORT) { [int]$env:SECUREFED_UI_PORT } else { 5173 }
$dashboardUrl = "http://127.0.0.1:$uiPort"
if ($env:SECUREFED_API_PORT) { $env:VITE_API_BASE_URL = "http://127.0.0.1:$([int]$env:SECUREFED_API_PORT)" }
$dashboard = try { Invoke-WebRequest $dashboardUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop } catch { $null }
if ($dashboard -and $dashboard.Content -match '<title>SecureFed-IDS Console</title>') {
    Write-Host "SecureFed-IDS dashboard is already running at $dashboardUrl"
} else {
    Push-Location -LiteralPath $frontendDir -ErrorAction Stop
    try {
        npm.cmd run dev -- --host 127.0.0.1 --port $uiPort --strictPort
    } finally {
        Pop-Location
    }
}
