param(
  [Parameter(Mandatory = $true, Position = 0)]
  [ValidateSet('setup', 'dev', 'stop', 'migrate', 'lint', 'typecheck', 'test', 'build')]
  [string]$Task
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $repo
try {
  function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
  }

  function New-Secret {
    $bytes = [byte[]]::new(48)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
  }

  function Get-ComposeArgs {
    return @('-f', 'docker-compose.yml', '-f', 'docker-compose.dev.yml')
  }

  function Get-FreePort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try { return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port }
    finally { $listener.Stop() }
  }

  switch ($Task) {
    'setup' {
      if (-not (Test-Path '.env')) {
        $dbPassword = New-Secret
        $config = @"
PUBLIC_ORIGIN=http://localhost:3000
SECURE_COOKIES=false
SETUP_TOKEN=$(New-Secret)
CSRF_SIGNING_SECRET=$(New-Secret)
SESSION_LIFETIME_HOURS=24
POSTGRES_PASSWORD=$dbPassword
DATABASE_URL=postgresql+asyncpg://bbd:${dbPassword}@postgres:5432/bbd
REDIS_URL=redis://redis:6379/0
DATA_DIR=/data
WEB_PORT=3000
OMNIROUTE_BASE_URL=
OMNIROUTE_API_KEY=
"@
        [System.IO.File]::WriteAllText((Join-Path $repo '.env'), $config, [System.Text.UTF8Encoding]::new($false))
        Write-Output 'Created local .env with generated secrets. Keep it private.'
      } else {
        Write-Output 'Kept existing .env unchanged.'
      }
      Invoke-Checked 'uv' @('sync', '--frozen')
      Invoke-Checked 'npm' @('ci')
    }
    'dev' { Invoke-Checked 'docker' (@('compose') + (Get-ComposeArgs) + @('up', '-d', '--build')) }
    'stop' { Invoke-Checked 'docker' (@('compose') + (Get-ComposeArgs) + @('stop')) }
    'migrate' { Invoke-Checked 'docker' (@('compose') + (Get-ComposeArgs) + @('run', '--rm', 'migrate')) }
    'lint' {
      Invoke-Checked 'uv' @('run', 'ruff', 'check', 'core', 'apps', 'tests', 'infrastructure/postgres/migrations')
      Invoke-Checked 'npm' @('run', 'lint')
    }
    'typecheck' {
      Invoke-Checked 'uv' @('run', 'mypy', 'core', 'apps')
      Invoke-Checked 'npm' @('run', 'typecheck')
    }
    'test' {
      $project = 'bbd-os-test-' + [guid]::NewGuid().ToString('N').Substring(0, 10)
      $compose = @('compose', '-p', $project, '-f', 'docker-compose.yml', '-f', 'docker-compose.test.yml')
      $previousWebPort = $env:WEB_PORT
      $previousApiTestPort = $env:API_TEST_PORT
      $previousIntegration = $env:BBD_INTEGRATION
      $previousApiUrl = $env:BBD_API_URL
      $previousTestOrigin = $env:TEST_PUBLIC_ORIGIN
      $previousE2eToken = $env:E2E_SETUP_TOKEN
      $previousPlaywrightUrl = $env:PLAYWRIGHT_BASE_URL
      $previousExternalServer = $env:PLAYWRIGHT_EXTERNAL_SERVER
      $webPort = Get-FreePort
      $apiPort = Get-FreePort
      while ($apiPort -eq $webPort) { $apiPort = Get-FreePort }
      try {
        $env:WEB_PORT = [string]$webPort
        $env:API_TEST_PORT = [string]$apiPort
        $env:TEST_PUBLIC_ORIGIN = "http://localhost:$webPort"
        Invoke-Checked 'docker' ($compose + @('up', '-d', '--build'))
        # `up` waits for migration completion; this second run proves the revision is idempotent.
        Invoke-Checked 'docker' ($compose + @('run', '--rm', 'migrate'))
        Invoke-Checked 'uv' @('run', 'pytest', '-q')
        $env:BBD_INTEGRATION = '1'
        $env:BBD_API_URL = "http://localhost:$apiPort"
        Invoke-Checked 'uv' @('run', 'pytest', 'tests/integration', '-q')
        Invoke-Checked 'docker' ($compose + @('exec', '-T', 'postgres', 'psql', '-U', 'bbd_test', '-d', 'bbd_test', '-c', 'TRUNCATE auth_session, owner CASCADE'))
        $env:E2E_SETUP_TOKEN = 'bbd-os-disposable-test-token'
        $env:PLAYWRIGHT_BASE_URL = "http://localhost:$webPort"
        $env:PLAYWRIGHT_EXTERNAL_SERVER = '1'
        Invoke-Checked 'npm' @('run', 'test:e2e')
      } finally {
        & docker @($compose + @('down', '--volumes', '--remove-orphans'))
        if ($null -eq $previousWebPort) { Remove-Item Env:WEB_PORT -ErrorAction SilentlyContinue }
        else { $env:WEB_PORT = $previousWebPort }
        if ($null -eq $previousApiTestPort) { Remove-Item Env:API_TEST_PORT -ErrorAction SilentlyContinue }
        else { $env:API_TEST_PORT = $previousApiTestPort }
        if ($null -eq $previousIntegration) { Remove-Item Env:BBD_INTEGRATION -ErrorAction SilentlyContinue }
        else { $env:BBD_INTEGRATION = $previousIntegration }
        if ($null -eq $previousApiUrl) { Remove-Item Env:BBD_API_URL -ErrorAction SilentlyContinue }
        else { $env:BBD_API_URL = $previousApiUrl }
        if ($null -eq $previousTestOrigin) { Remove-Item Env:TEST_PUBLIC_ORIGIN -ErrorAction SilentlyContinue }
        else { $env:TEST_PUBLIC_ORIGIN = $previousTestOrigin }
        if ($null -eq $previousE2eToken) { Remove-Item Env:E2E_SETUP_TOKEN -ErrorAction SilentlyContinue }
        else { $env:E2E_SETUP_TOKEN = $previousE2eToken }
        if ($null -eq $previousPlaywrightUrl) { Remove-Item Env:PLAYWRIGHT_BASE_URL -ErrorAction SilentlyContinue }
        else { $env:PLAYWRIGHT_BASE_URL = $previousPlaywrightUrl }
        if ($null -eq $previousExternalServer) { Remove-Item Env:PLAYWRIGHT_EXTERNAL_SERVER -ErrorAction SilentlyContinue }
        else { $env:PLAYWRIGHT_EXTERNAL_SERVER = $previousExternalServer }
      }
    }
    'build' {
      Invoke-Checked 'npm' @('run', 'build')
      Invoke-Checked 'docker' @('compose', '-f', 'docker-compose.yml', 'build')
    }
  }
} finally {
  Pop-Location
}
