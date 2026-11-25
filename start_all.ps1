# Windows-native SecureFed-IDS launcher. Run from either PowerShell edition.
$ErrorActionPreference = 'Stop'
$apiPort = if ($env:SECUREFED_API_PORT) { [int]$env:SECUREFED_API_PORT } else { 8000 }
$uiPort = if ($env:SECUREFED_UI_PORT) { [int]$env:SECUREFED_UI_PORT } else { 5173 }
$projectRoot = $PSScriptRoot
$node = Get-Command node -ErrorAction Stop
$npm = Get-Command npm.cmd -ErrorAction Stop
$backendPython = if ($env:VIRTUAL_ENV) { Join-Path $env:VIRTUAL_ENV 'Scripts/python.exe' }
foreach ($relative in '.venv/Scripts/python.exe','web/backend/.venv-tf/Scripts/python.exe') {
    if (!$backendPython -and (Test-Path -LiteralPath (Join-Path $projectRoot $relative))) { $backendPython = Join-Path $projectRoot $relative }
}
if (!$backendPython) { $backendPython = (Get-Command python -ErrorAction Stop).Source }
& $backendPython -c "import fastapi, sqlalchemy, uvicorn, numpy, tensorflow"
if ($LASTEXITCODE) { throw 'Install the backend and training requirements in the project Python environment. See memory.md.' }
if (!(Test-Path -LiteralPath (Join-Path $projectRoot 'web/frontend/node_modules/vite'))) { throw 'Run npm.cmd ci in web/frontend first.' }
function Start-LocalService($scriptName, $url, $expected) {
    $testService = { try { (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2).Content -match $expected } catch { $false } }
    if (& $testService) { return }
    $scriptPath = Join-Path $projectRoot $scriptName
    $log = Join-Path $env:TEMP ("SecureFed-" + [guid]::NewGuid().ToString("N"))
    $process = Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $scriptPath + '"')) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput ($log+'.out') -RedirectStandardError ($log+'.err')
    for ($attempt=0; $attempt -lt 45; $attempt++) {
        if (& $testService) { return }
        if ($process.HasExited) { break }
        Start-Sleep -Milliseconds 500
    }
    throw "Startup failed for $scriptName. See $log.err"
}
Start-LocalService 'start_backend.ps1' "http://127.0.0.1:$apiPort/api/v1/version" 'SecureFed-IDS API'
$null = Invoke-RestMethod -Uri "http://127.0.0.1:$apiPort/api/v1/health"
try { $null = Invoke-RestMethod -Uri "http://127.0.0.1:$apiPort/api/v1/native-network" } catch { throw "Native network API unavailable. Stop the older project backend with .\stop_services.ps1 and restart." }
Start-LocalService 'start_frontend.ps1' "http://127.0.0.1:$uiPort" 'SecureFed-IDS Console'
Write-Host "Dashboard: http://127.0.0.1:$uiPort/sdn"
Write-Host 'Stop both services with .\stop_services.ps1'
