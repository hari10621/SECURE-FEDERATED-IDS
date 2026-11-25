# Stop the local development servers after confirming their project and command lines.
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path $PSScriptRoot).Path
$apiPort = if ($env:SECUREFED_API_PORT) { [int]$env:SECUREFED_API_PORT } else { 8000 }
$uiPort = if ($env:SECUREFED_UI_PORT) { [int]$env:SECUREFED_UI_PORT } else { 5173 }
foreach ($port in $uiPort, $apiPort) {
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
    foreach ($listenerId in @($listeners.OwningProcess | Where-Object { $_ } | Select-Object -Unique)) {
        $service = Get-CimInstance Win32_Process -Filter "ProcessId=$listenerId"
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($service.ParentProcessId)"
        $projectCommand = "$($service.CommandLine) $($parent.CommandLine)"
        $projectMatch = $projectCommand.IndexOf("$projectRoot\", [StringComparison]::OrdinalIgnoreCase) -ge 0
        $expected = if ($port -eq $uiPort) { 'vite' } else { 'uvicorn\s+app\.main:app' }
        if (-not $projectMatch -or $service.CommandLine -notmatch $expected) {
            throw "Cannot verify the project owning port $port. Stop its original terminal with Ctrl+C."
        }
        Stop-Process -Id $listenerId
        Write-Host "Stopped SecureFed-IDS on port $port."
    }
}
