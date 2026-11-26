function Initialize-BackendEnvironment {
    param([string]$Root, [string]$CacheRoot)

    $cacheRoot = [IO.Path]::GetFullPath($CacheRoot)
    if ([IO.Path]::GetPathRoot($Root) -ne 'D:\' -or [IO.Path]::GetPathRoot($cacheRoot) -ne 'D:\') {
        throw 'FoodDiary and its development cache must be on D:.'
    }
    $env:PIP_CACHE_DIR = Join-Path $cacheRoot 'pip-cache'
    $env:TEMP = Join-Path $cacheRoot 'tmp'
    $env:TMP = $env:TEMP
    $env:TMPDIR = $env:TEMP
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    # Ignore machine-level pip target/prefix settings for this checkout.
    $env:PIP_CONFIG_FILE = 'nul'
    foreach ($name in 'PIP_TARGET','PIP_PREFIX','PIP_USER','PIP_ROOT') {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
    New-Item -ItemType Directory -Path $env:PIP_CACHE_DIR,$env:TEMP -Force | Out-Null
}

function Initialize-LocalDatabase {
    param([string]$Root, [int]$FrontendPort)
    $backend = Join-Path $Root 'backend'
    $data = Join-Path $backend 'data'
    New-Item -ItemType Directory -Path $data,(Join-Path $backend 'logs') -Force | Out-Null

    # A supplied .env or environment configuration takes precedence.
    if (-not $env:JWT_SECRET -and -not (Test-Path -LiteralPath (Join-Path $Root '.env'))) {
        if ($env:APP_ENV -and $env:APP_ENV -ne 'development') {
            throw 'Set JWT_SECRET explicitly outside development.'
        }
        $keyFile = Join-Path $data 'dev-jwt.key'
        if (-not (Test-Path -LiteralPath $keyFile)) {
            $random = [Security.Cryptography.RandomNumberGenerator]::Create()
            try {
                $bytes = [byte[]]::new(48)
                $random.GetBytes($bytes)
                try {
                    $keyStream = [IO.File]::Open($keyFile, [IO.FileMode]::CreateNew)
                    try {
                        $writer = [IO.StreamWriter]::new($keyStream)
                        try { $writer.Write([Convert]::ToBase64String($bytes)) } finally { $writer.Dispose() }
                    } finally { $keyStream.Dispose() }
                } catch [IO.IOException] {
                    if (-not (Test-Path -LiteralPath $keyFile)) { throw }
                }
            } finally { $random.Dispose() }
        }
        $env:JWT_SECRET = [IO.File]::ReadAllText($keyFile).Trim()
    }
    if (-not $env:APP_ORIGINS -and -not (Test-Path -LiteralPath (Join-Path $Root '.env'))) {
        $env:APP_ORIGINS = '["http://127.0.0.1:' + $FrontendPort + '"]'
    }
}

function Assert-FreeLocalPort {
    param([int]$Port)
    $socket = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
    try { $socket.Start() }
    catch [Net.Sockets.SocketException] { throw "Port $Port is already in use or unavailable." }
    finally { $socket.Stop() }
}
