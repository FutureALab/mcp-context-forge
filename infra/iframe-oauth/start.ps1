param([string]$Python = 'I:\anaconda\envs\py312\python.exe')
$ErrorActionPreference = 'Stop'
$demoRoot = $PSScriptRoot
$runtime = Join-Path $demoRoot '.runtime'
foreach ($port in @(18080, 18081, 4446)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use. Stop this demo or choose unused ports before starting."
    }
}
& $Python (Join-Path $demoRoot 'run_gateway.py') prepare
if ($LASTEXITCODE -ne 0) { throw 'Demo preparation failed.' }
try {
    & docker compose -f (Join-Path $demoRoot 'compose.yaml') up -d --pull never
    if ($LASTEXITCODE -ne 0) { throw 'Docker startup failed.' }
    $gatewayProcess = Start-Process -FilePath $Python -ArgumentList @("`"$(Join-Path $demoRoot 'run_gateway.py')`"", 'gateway') -WorkingDirectory $demoRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'gateway.stdout.log') -RedirectStandardError (Join-Path $runtime 'gateway.stderr.log')
    $gatewayProcess.Id | Set-Content (Join-Path $runtime 'gateway.pid')
    $ready = $false
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        if ($gatewayProcess.HasExited) { throw 'Gateway exited. Read .runtime/gateway.stderr.log.' }
        try {
            $providers = Invoke-RestMethod 'http://localhost:18081/auth/sso/providers' -TimeoutSec 3
            if ($providers.id -contains 'intranet-demo') { $ready = $true; break }
        } catch { }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw 'Gateway startup timed out. Read .runtime/gateway.stderr.log.' }
    Write-Output 'Demo ready: http://localhost:18080'
    Write-Output "Test account: $runtime\account.txt"
} catch {
    & (Join-Path $demoRoot 'stop.ps1')
    throw
}
