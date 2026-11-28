param([string]$OutputRoot = 'D:\DevEnv\fooddiary-phase72\releases')

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if ([IO.Path]::GetPathRoot($OutputRoot) -ne 'D:\') { throw 'Release staging must be on D:.' }
Push-Location $root
try {
    if (git status --porcelain -- frontend backend deploy scripts) { throw 'Commit release inputs first.' }
    $sha = git rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $sha -notmatch '^[a-f0-9]{40}$') { throw 'Invalid release commit.' }
    $target = Join-Path $OutputRoot $sha
    if (Test-Path -LiteralPath $target) { throw "Release already exists: $target" }
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
    $stage = Join-Path $OutputRoot ('.stage-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $stage | Out-Null
    & (Join-Path $PSScriptRoot 'setup-dev-env.ps1') -Action Build -Mode Api
    $archive = Join-Path $stage 'inputs.tar'
    git archive --format=tar --output=$archive $sha backend/app backend/migrations backend/alembic.ini backend/requirements.txt backend/requirements-sticker.txt deploy/production
    if ($LASTEXITCODE -ne 0) { throw 'Unable to read Git release inputs.' }
    tar.exe -xf $archive -C $stage
    if ($LASTEXITCODE -ne 0) { throw 'Unable to extract release inputs.' }
    Remove-Item -LiteralPath $archive
    Copy-Item -LiteralPath (Join-Path $root 'frontend/dist') -Destination (Join-Path $stage 'web') -Recurse
    [IO.File]::WriteAllText((Join-Path $stage 'REVISION'), $sha + "`n")
    $python = Join-Path $root 'backend/.venv/Scripts/python.exe'
    $manifest = Join-Path $stage 'deploy/production/release-manifest.py'
    & $python $manifest write $stage $sha
    if ($LASTEXITCODE -ne 0) { throw 'Could not write release checksums.' }
    [IO.Directory]::Move($stage, $target)
    $target
} finally {
    Pop-Location
}
