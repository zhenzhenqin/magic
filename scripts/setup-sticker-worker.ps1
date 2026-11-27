param(
    [ValidateSet('Check','Install')][string]$Action = 'Check',
    [string]$DevEnvRoot = 'D:\DevEnv'
)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'backend-env.ps1')
Initialize-BackendEnvironment -Root $project -CacheRoot $DevEnvRoot
$venv = Join-Path $DevEnvRoot 'fooddiary-phase5/worker'
$python = Join-Path $venv 'Scripts/python.exe'
$modelDir = Join-Path $DevEnvRoot 'models/rembg'
$weights = Join-Path $modelDir 'u2netp.onnx'
$sha = '309C8469258DDA742793DCE0EBEA8E6DD393174F89934733ECC8B14C76F4DDD8'
$env:REMBG_HOME = $env:U2NET_HOME = $modelDir
$env:OMP_NUM_THREADS = '1'

if ($Action -eq 'Install') {
    $system = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
    if ($system.FreeSpace -lt 10GB -or (Get-PSDrive D).Free -lt 2GB) { throw 'Insufficient free space for the isolated Worker.' }
    New-Item -ItemType Directory -Path $venv,$modelDir -Force | Out-Null
    if (-not (Test-Path -LiteralPath $python)) {
        py -3.13 -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the D: Sticker Worker environment.' }
    }
    & $python -c 'import sys,tempfile; assert sys.version_info[:2] == (3,13); print(sys.prefix, tempfile.gettempdir())'
    if ($LASTEXITCODE -ne 0) { throw 'Unexpected worker Python or temporary path.' }
    & $python -m pip cache dir
    & $python -m pip install --timeout 20 --only-binary=:all: -r (Join-Path $project 'backend/requirements.txt') -r (Join-Path $project 'backend/requirements-sticker.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Sticker Worker dependencies did not install.' }
    if (-not (Test-Path -LiteralPath $weights)) {
        $partial = Join-Path $modelDir 'u2netp.onnx.partial'
        Invoke-WebRequest -Uri 'https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx' -OutFile $partial
        if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash -ne $sha) { throw 'Downloaded weight checksum differs.' }
        Move-Item -LiteralPath $partial -Destination $weights
    }
    $after = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
    if ($system.FreeSpace - $after.FreeSpace -gt 500MB) { throw 'C: free space decreased by more than 500 MiB.' }
}

if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $weights)) { throw 'Run this script with -Action Install first.' }
if ((Get-FileHash -LiteralPath $weights -Algorithm SHA256).Hash -ne $sha) { throw 'Cached weight checksum differs.' }
& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Sticker Worker dependency compatibility check failed.' }
Push-Location (Join-Path $project 'backend')
try {
    & $python -c 'import importlib.metadata as md,os; from pathlib import Path; from app.services.sticker_image import OnnxBackgroundRemovalProvider; model=OnnxBackgroundRemovalProvider(Path(os.environ["REMBG_HOME"]),1); print(md.version("numpy"),md.version("onnxruntime"),model.session.get_providers())'
    if ($LASTEXITCODE -ne 0) { throw 'Could not open the verified CPU model.' }
} finally { Pop-Location }
Get-Item -LiteralPath $weights | Select-Object FullName,Length
