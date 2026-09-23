$ErrorActionPreference = 'Stop'
$pidFile = Join-Path $PSScriptRoot '.runtime/gateway.pid'
if (Test-Path -LiteralPath $pidFile) {
    $gatewayPid = [int](Get-Content -LiteralPath $pidFile)
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $gatewayPid"
    $expectedScript = Join-Path $PSScriptRoot 'run_gateway.py'
    if ($process) {
        if (-not $process.CommandLine.Contains($expectedScript) -or -not $process.CommandLine.Contains('gateway')) {
            throw "PID $gatewayPid no longer belongs to this demo. Refusing to stop it."
        }
        Stop-Process -Id $gatewayPid
        Wait-Process -Id $gatewayPid -Timeout 15 -ErrorAction SilentlyContinue
        if (Get-Process -Id $gatewayPid -ErrorAction SilentlyContinue) { throw 'Gateway is still running.' }
    }
    Remove-Item -LiteralPath $pidFile
}
& docker compose -f (Join-Path $PSScriptRoot 'compose.yaml') down
if ($LASTEXITCODE -ne 0) { throw 'Docker cleanup failed.' }
Write-Output 'Demo services stopped. Local demo data is preserved.'
