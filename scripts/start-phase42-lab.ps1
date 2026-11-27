param(
    [switch]$PrepareOnly,
    [ValidateRange(0, 1000)]
    [int]$AuthorizedCallLimit = 0,
    [string[]]$BenchmarkOptions
)

$ErrorActionPreference = 'Stop'
$lab = 'D:\DevEnv\fooddiary-phase42'
$db = Join-Path $lab 'benchmark.db'
$jwtFile = Join-Path $lab 'jwt.key'
$providerFile = Join-Path $lab 'provider.env'
$firstSetup = -not (Test-Path -LiteralPath $lab)

if ($PrepareOnly -and $AuthorizedCallLimit) { throw 'Preparing the lab requires a zero call limit.' }
if ($BenchmarkOptions -and ($PrepareOnly -or -not $AuthorizedCallLimit)) {
    throw 'A live benchmark requires a previously approved, positive cumulative limit.'
}
if ($firstSetup) {
    if (-not $PrepareOnly) { throw 'Initialize the isolated lab first with -PrepareOnly.' }
    $directory = New-Item -ItemType Directory -Path $lab
    $access = Get-Acl -LiteralPath $directory.FullName
    $access.SetAccessRuleProtection($true, $false)
    foreach ($identity in @([Security.Principal.WindowsIdentity]::GetCurrent().User, [Security.Principal.SecurityIdentifier]::new('S-1-5-18'))) {
        $rule = [Security.AccessControl.FileSystemAccessRule]::new(
            $identity, 'FullControl', 'ContainerInherit, ObjectInherit', 'None', 'Allow'
        )
        $access.SetAccessRule($rule)
    }
    Set-Acl -LiteralPath $directory.FullName -AclObject $access
    $key = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(48))
    [IO.File]::WriteAllText($jwtFile, $key)
    New-Item -ItemType Directory -Path (Join-Path $lab 'media'),(Join-Path $lab 'reports') | Out-Null
} elseif (-not (Test-Path -LiteralPath $db -PathType Leaf) -or -not (Test-Path -LiteralPath $jwtFile -PathType Leaf)) {
    throw 'Restore the existing lab ledger and key. This script will not recreate a missing ledger.'
}

if ($PrepareOnly -and -not (Test-Path -LiteralPath $providerFile)) {
    [IO.File]::WriteAllText($providerFile, "AI_BASE_URL=`r`nAI_API_KEY=`r`n")
}

$frontendPort = 15176
$backendPort = 18022
$settings = @{
    APP_ENV = 'development'
    DATABASE_URL = 'sqlite:///' + $db.Replace('\', '/')
    MEDIA_DIR = Join-Path $lab 'media'
    JWT_SECRET = [IO.File]::ReadAllText($jwtFile)
    APP_ORIGINS = '["http://127.0.0.1:15176"]'
    AI_ENABLED = if ($AuthorizedCallLimit) { 'true' } else { 'false' }
    AI_PROVIDER = 'qwen'
    AI_MODEL = 'qwen3-vl-flash'
    AI_USER_DAILY_LIMIT = [string][Math]::Max(1, $AuthorizedCallLimit)
    AI_GLOBAL_DAILY_LIMIT = [string][Math]::Max(1, $AuthorizedCallLimit)
    AI_QWEN_CUMULATIVE_LIMIT = [string]$AuthorizedCallLimit
    AI_MAX_CONCURRENT_JOBS = '1'
    AI_MAX_ATTEMPTS = '1'
    AI_MAX_OUTPUT_TOKENS = '1024'
    TEMP = 'D:\DevEnv\tmp'
    TMP = 'D:\DevEnv\tmp'
    TMPDIR = 'D:\DevEnv\tmp'
}

if ($AuthorizedCallLimit) {
    $provider = @{}
    foreach ($line in [IO.File]::ReadLines($providerFile)) {
        if ($line -match '^(AI_BASE_URL|AI_API_KEY)=(.+)$') { $provider[$Matches[1]] = $Matches[2].Trim() }
    }
    if (-not $provider.AI_API_KEY -or -not $provider.AI_BASE_URL) {
        throw 'Fill the private lab provider.env with the approved workspace URL and key.'
    }
    $settings.AI_BASE_URL = $provider.AI_BASE_URL
    $settings.AI_API_KEY = $provider.AI_API_KEY
}

$previous = @{}
try {
    foreach ($name in $settings.Keys) {
        $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $settings[$name], 'Process')
    }
    if ($BenchmarkOptions) {
        Push-Location (Join-Path (Split-Path -Parent $PSScriptRoot) 'backend')
        try {
            & .\.venv\Scripts\python.exe -m tests.ai_benchmark @BenchmarkOptions --run-local qwen --base-url "http://127.0.0.1:$frontendPort" --database $db
            if ($LASTEXITCODE -ne 0) { throw "Benchmark paused or failed (exit $LASTEXITCODE). Consult the private report." }
        } finally {
            Pop-Location
        }
    } elseif ($PrepareOnly) {
        & (Join-Path $PSScriptRoot 'setup-backend.ps1') -Action Migrate
        "Phase 4.2 lab prepared with real calls disabled at $lab"
    } else {
        & (Join-Path $PSScriptRoot 'setup-backend.ps1') -Action Migrate
        & (Join-Path $PSScriptRoot 'start-dev.ps1') -FrontendPort $frontendPort -BackendPort $backendPort -WithAiWorker:([bool]$AuthorizedCallLimit)
    }
} finally {
    foreach ($name in $previous.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
}
