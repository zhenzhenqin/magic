param(
    [ValidateSet('Check', 'Install', 'Dev', 'Typecheck', 'Build', 'Test', 'Screenshots', 'TestApi', 'ScreenshotsApi', 'ScreenshotsDiary', 'TestAi', 'ScreenshotsAi')]
    [string]$Action = 'Dev',
    [string]$DevEnvRoot = 'D:\DevEnv',
    [int]$Port = 5173,
    [int]$BackendPort = 8000,
    [ValidateSet('Api', 'Demo')]
    [string]$Mode = 'Demo'
)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $project 'frontend'
$cacheRoot = [IO.Path]::GetFullPath($DevEnvRoot)
if ([IO.Path]::GetPathRoot($cacheRoot) -ne 'D:\' -or [IO.Path]::GetPathRoot($project) -ne 'D:\') {
    throw 'FoodDiary and its development cache must be on D:.'
}

$buildMode = if ($Action -eq 'Build' -and -not $PSBoundParameters.ContainsKey('Mode')) { 'Api' } else { $Mode }
$settings = @{
    npm_config_store_dir = Join-Path $cacheRoot 'pnpm-store'
    npm_config_cache_dir = Join-Path $cacheRoot 'pnpm-store\metadata'
    npm_config_state_dir = Join-Path $cacheRoot 'pnpm-store\state'
    npm_config_cache = Join-Path $cacheRoot 'npm-cache'
    PLAYWRIGHT_BROWSERS_PATH = Join-Path $cacheRoot 'playwright'
    TEMP = Join-Path $cacheRoot 'tmp'
    TMP = Join-Path $cacheRoot 'tmp'
    TMPDIR = Join-Path $cacheRoot 'tmp'
    FOODDIARY_PORT = [string]$Port
    FOODDIARY_BACKEND_PORT = [string]$BackendPort
    FOODDIARY_BROWSER_FAKE_AI = if ($Action -in 'TestAi', 'ScreenshotsAi') { '1' } else { '0' }
    VITE_APP_MODE = $buildMode.ToLowerInvariant()
}

$oldEnvironment = @{}
Push-Location $frontend
try {
    foreach ($name in $settings.Keys) {
        $oldEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $settings[$name], 'Process')
    }
    foreach ($folder in @($env:npm_config_store_dir, $env:npm_config_cache, $env:PLAYWRIGHT_BROWSERS_PATH, $env:TEMP)) {
        New-Item -ItemType Directory -Path $folder -Force | Out-Null
    }

    if ($Action -in 'Check', 'Install') {
        $actualStore = ((& pnpm store path) | Select-Object -Last 1).Trim()
        $actualMetadata = ((& pnpm config get cache-dir) | Select-Object -Last 1).Trim()
        $actualNpm = ((& npm.cmd config get cache) | Select-Object -Last 1).Trim()
        $storePrefix = $env:npm_config_store_dir.TrimEnd('\') + '\'
        if (-not $actualStore.StartsWith($storePrefix, [StringComparison]::OrdinalIgnoreCase) -or
            $actualMetadata -ne $env:npm_config_cache_dir -or $actualNpm -ne $env:npm_config_cache) {
            throw "Unexpected cache paths. pnpm: $actualStore, metadata: $actualMetadata, npm: $actualNpm"
        }
        Write-Output "pnpm store: $actualStore"
        Write-Output "pnpm metadata: $actualMetadata"
        Write-Output "npm cache: $actualNpm"
        Write-Output "PLAYWRIGHT_BROWSERS_PATH: $env:PLAYWRIGHT_BROWSERS_PATH"
        Write-Output "TEMP / TMP / TMPDIR: $env:TEMP"
        $systemDisk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
        if ($Action -eq 'Install' -and $systemDisk.FreeSpace -lt 10GB) {
            throw 'C: has less than 10 GiB available. Installation paused.'
        }
    }

    switch ($Action) {
        'Check' {}
        'Install' {
            if (Test-Path -LiteralPath 'pnpm-lock.yaml') { & pnpm install --frozen-lockfile }
            else { & pnpm install }
        }
        'Dev' { & pnpm dev --host 127.0.0.1 --port $Port --strictPort }
        'Typecheck' { & pnpm typecheck }
        'Build' { & pnpm build }
        'Test' { & pnpm test }
        'Screenshots' { & pnpm screenshots }
        'TestApi' { & pnpm exec playwright test --config playwright.api.config.ts --grep-invert '@screenshots|@fake-ai' }
        'ScreenshotsApi' { & pnpm exec playwright test --config playwright.api.config.ts auth.api.spec.ts --grep '@screenshots' --reporter=list }
        'ScreenshotsDiary' { & pnpm exec playwright test --config playwright.api.config.ts meal.api.spec.ts --grep '@screenshots' --reporter=list }
        'TestAi' { & pnpm exec playwright test --config playwright.api.config.ts ai.api.spec.ts --grep '@fake-ai' --grep-invert '@screenshots' }
        'ScreenshotsAi' { & pnpm exec playwright test --config playwright.api.config.ts ai.api.spec.ts --grep '@screenshots' --reporter=list }
    }
    if ($LASTEXITCODE -ne 0) { throw "FoodDiary action '$Action' exited with code $LASTEXITCODE." }
}
finally {
    Pop-Location
    foreach ($name in $oldEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $oldEnvironment[$name], 'Process')
    }
}
