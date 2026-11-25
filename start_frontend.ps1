$projectRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$frontendDir = Join-Path $projectRoot 'web/frontend'
if (-not (Test-Path (Join-Path $frontendDir 'package.json'))) {
    throw 'Open PowerShell in the SecureFed-IDS project folder and run .\start_frontend.ps1.'
}
$dashboardUrl = 'http://127.0.0.1:5173'
$dashboard = try { Invoke-WebRequest $dashboardUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop } catch { $null }
if ($dashboard -and $dashboard.Content -match '<title>SecureFed-IDS Console</title>') {
    Write-Host "SecureFed-IDS dashboard is already running at $dashboardUrl"
} else {
    Push-Location -LiteralPath $frontendDir -ErrorAction Stop
    try {
        npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
    } finally {
        Pop-Location
    }
}
