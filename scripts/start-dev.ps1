param(
    [ValidateSet('Api','Demo')]
    [string]$Mode = 'Api',
    [string]$DevEnvRoot = 'D:\DevEnv',
    [int]$FrontendPort = 5173,
    [int]$BackendPort = 8000,
    [switch]$WithAiWorker
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'backend-env.ps1')
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$frontendScript = Join-Path $PSScriptRoot 'setup-dev-env.ps1'
Assert-FreeLocalPort -Port $FrontendPort
if ($Mode -eq 'Demo') {
    & $frontendScript -Action Dev -Mode Demo -Port $FrontendPort -DevEnvRoot $DevEnvRoot
    return
}
Assert-FreeLocalPort -Port $BackendPort
if (-not (Test-Path -LiteralPath $python)) { throw 'Run setup-backend.ps1 -Action Install first.' }

$names = 'PIP_CACHE_DIR','TEMP','TMP','TMPDIR','PIP_DISABLE_PIP_VERSION_CHECK','PIP_CONFIG_FILE','PIP_TARGET','PIP_PREFIX','PIP_USER','PIP_ROOT','JWT_SECRET','APP_ORIGINS'
$previous = @{}
foreach ($name in $names) { $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }

$process = $null
$worker = $null
try {
    Initialize-BackendEnvironment -Root $root -CacheRoot $DevEnvRoot
    Initialize-LocalDatabase -Root $root -FrontendPort $FrontendPort
    $stamp = [guid]::NewGuid().ToString('N')
    $stdout = Join-Path $backend "logs/dev-$stamp.out.log"
    $stderr = Join-Path $backend "logs/dev-$stamp.err.log"
    $process = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','app.main:create_app','--factory','--host','127.0.0.1','--port',"$BackendPort",'--no-proxy-headers') -WorkingDirectory $backend -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru

    $ready = $false
    for ($attempt = 0; $attempt -lt 40 -and -not $process.HasExited; $attempt++) {
        try {
            $response = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/v1/ready" -TimeoutSec 1
            if ($response.status -eq 'ready') { $ready = $true; break }
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $ready) { throw "API is not ready. Run setup-backend.ps1 -Action Migrate and check $stderr" }
    "FoodDiary API: http://127.0.0.1:$BackendPort/docs"
    if ($WithAiWorker) {
        $workerOut = Join-Path $backend "logs/ai-$stamp.out.log"
        $workerErr = Join-Path $backend "logs/ai-$stamp.err.log"
        $worker = Start-Process -FilePath $python -ArgumentList @('-m','app.ai_worker') -WorkingDirectory $backend -WindowStyle Hidden -RedirectStandardOutput $workerOut -RedirectStandardError $workerErr -PassThru
        "FoodDiary AI worker log: $workerErr"
    }
    & $frontendScript -Action Dev -Mode Api -Port $FrontendPort -BackendPort $BackendPort -DevEnvRoot $DevEnvRoot
}
finally {
    if ($worker -and -not $worker.HasExited) { Stop-Process -InputObject $worker }
    if ($process -and -not $process.HasExited) { Stop-Process -InputObject $process }
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process') }
}
