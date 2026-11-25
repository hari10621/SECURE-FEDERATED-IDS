$projectRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$backendDir = Join-Path $projectRoot 'web/backend'
if (-not (Test-Path (Join-Path $backendDir 'app/main.py'))) {
    throw 'Open PowerShell in the SecureFed-IDS project folder and run .\start_backend.ps1.'
}
$env:SECUREFED_ENABLE_TRAINING = 'true'
$env:SECUREFED_ENABLE_PREDICTIONS = 'true'
$labCredential = Join-Path $projectRoot 'web/var/sdn-agent.credential.xml'
if (-not $env:SECUREFED_LAB_TOKEN -and (Test-Path -LiteralPath $labCredential)) {
    $env:SECUREFED_LAB_TOKEN = (Import-Clixml -LiteralPath $labCredential).GetNetworkCredential().Password
}
if (-not $env:SECUREFED_ENABLE_CKKS) { $env:SECUREFED_ENABLE_CKKS = 'true' }
$backendUrl = 'http://127.0.0.1:8000'
$apiVersion = try { Invoke-RestMethod "$backendUrl/api/v1/version" -TimeoutSec 2 -ErrorAction Stop } catch { $null }
if ($apiVersion.name -eq 'SecureFed-IDS API') {
    Write-Host "SecureFed-IDS backend is already running at $backendUrl"
} else {
    $backendPython = 'python'
    if (-not $env:VIRTUAL_ENV) {
        foreach ($candidate in '.venv/Scripts/python.exe', 'web/backend/.venv-tf/Scripts/python.exe') {
            $localPython = Join-Path $projectRoot $candidate
            if (Test-Path $localPython) {
                $backendPython = $localPython
                break
            }
        }
    }
    Push-Location -LiteralPath $backendDir -ErrorAction Stop
    try {
        & $backendPython -m uvicorn app.main:app --host 127.0.0.1 --port 8000
    } finally {
        Pop-Location
    }
}
