param(
    [ValidateSet('Install','Migrate','CheckSchema','Dev','Test','Benchmark','MediaCleanup','BenchmarkImages','AiWorker')]
    [string]$Action = 'Install',
    [string]$DevEnvRoot = 'D:\DevEnv',
    [int]$Port = 8000,
    [int]$FrontendPort = 5173,
    [switch]$ApplyCleanup
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'backend-env.ps1')
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$names = 'PIP_CACHE_DIR','TEMP','TMP','TMPDIR','PIP_DISABLE_PIP_VERSION_CHECK','PIP_CONFIG_FILE','PIP_TARGET','PIP_PREFIX','PIP_USER','PIP_ROOT','JWT_SECRET','APP_ORIGINS'
$previous = @{}
foreach ($name in $names) { $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }

Push-Location $backend
try {
    Initialize-BackendEnvironment -Root $root -CacheRoot $DevEnvRoot
    if ($Action -eq 'Install') {
        $before = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:' OR DeviceID='D:'"
        if (($before | Where-Object DeviceID -eq 'C:').FreeSpace -lt 10GB) {
            throw 'C: has less than 10 GiB available. Installation paused.'
        }
        $before | ForEach-Object { "Before installation $($_.DeviceID) $($_.FreeSpace) bytes" }
        $cache = & python -m pip cache dir
        if ($LASTEXITCODE -ne 0 -or $cache -ne $env:PIP_CACHE_DIR) { throw 'Unexpected pip cache' }
        & python -m pip config get global.target 2>$null
        if ($LASTEXITCODE -eq 0) { throw 'Unexpected global pip target' }
        "pip cache: $cache"
        if (-not (Test-Path -LiteralPath $python)) {
            & python -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python virtual environment.' }
        }
        & $python -c 'import sys, sysconfig; from pathlib import Path; root = Path(sys.prefix).resolve(); assert sys.prefix != sys.base_prefix and root == (Path.cwd() / ".venv").resolve() and Path(sysconfig.get_path("purelib")).resolve().is_relative_to(root)'
        if ($LASTEXITCODE -ne 0) { throw 'Pip installation must target the project virtual environment.' }
        & $python -m pip install --only-binary=:all: -r requirements.txt
        if ($LASTEXITCODE -ne 0) { throw 'Python dependencies could not be installed.' }
        & $python -m pip check
        if ($LASTEXITCODE -ne 0) { throw 'Python dependency compatibility check failed.' }
        & $python -c 'from pathlib import Path; import alembic, fastapi, sys; assert all(Path(module.__file__).is_relative_to(sys.prefix) for module in (alembic, fastapi))'
        if ($LASTEXITCODE -ne 0) { throw 'Backend packages must resolve from the project virtual environment.' }
        $after = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:' OR DeviceID='D:'"
        $after | ForEach-Object { "After installation $($_.DeviceID) $($_.FreeSpace) bytes" }
        $cBefore = ($before | Where-Object DeviceID -eq 'C:').FreeSpace
        $cAfter = ($after | Where-Object DeviceID -eq 'C:').FreeSpace
        if (($cBefore - $cAfter) -gt 500MB) { throw 'C: available space decreased by over 500 MiB. Check the source before continuing.' }
        return
    }
    if (-not (Test-Path -LiteralPath $python)) { throw 'Run setup-backend.ps1 -Action Install first.' }
    switch ($Action) {
        'Test' {
            $folder = Join-Path $env:TEMP ('fooddiary-auth-pytest-' + [guid]::NewGuid().ToString('N'))
            "Test temporary directory: $folder"
            & $python -m pytest -p no:cacheprovider --basetemp $folder
        }
        'Benchmark' { & $python -m tests.benchmark_passwords }
        'BenchmarkImages' { & $python -m tests.benchmark_images }
        default {
            Initialize-LocalDatabase -Root $root -FrontendPort $FrontendPort
            switch ($Action) {
                'Migrate' { & $python -m alembic upgrade head }
                'CheckSchema' { & $python -m alembic current; if ($LASTEXITCODE -eq 0) { & $python -m alembic check } }
                'AiWorker' { & $python -m app.ai_worker }
                'MediaCleanup' {
                    if ($ApplyCleanup) { & $python -m app.media_cleanup --apply }
                    else { & $python -m app.media_cleanup }
                }
                'Dev' {
                    Assert-FreeLocalPort -Port $Port
                    & $python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port $Port --no-proxy-headers
                }
            }
        }
    }
    if ($LASTEXITCODE -ne 0) { throw "Backend action '$Action' exited with code $LASTEXITCODE." }
}
finally {
    Pop-Location
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process') }
}
