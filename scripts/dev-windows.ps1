<#
.SYNOPSIS
  Windows-native dev runner: web (vite) + api (uvicorn) against the shared
  remote dev infra. No WSL, no local docker infra.

.DESCRIPTION
  - Loads repo-root .env.local into the process environment when the api is
    started (the api reads os.environ over its ENV_FILE, so a repo-root .env is
    not needed). WebOnly uses .env.local when present, otherwise existing env
    values and Vite defaults.
  - Starts the api by invoking the venv python directly. We do NOT use
    `uv run` here: it re-syncs against uv.lock on every start and would try to
    rebuild the locally-built y-py wheel from the registry sdist (which fails on
    Windows). The bootstrap installs y-py into the venv; this launcher just uses it.
  - Does NOT auto-migrate the shared dev DB (AI_DO_API_AUTO_MIGRATE=0). DB
    migrations are coordinated and applied from the server dev checkout.

.PARAMETER ApiOnly   Start only the api.
.PARAMETER WebOnly   Start only the web dev server.
#>
param(
  [switch]$ApiOnly,
  [switch]$WebOnly
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($ApiOnly -and $WebOnly) {
  throw "Choose only one of -ApiOnly or -WebOnly."
}

$envFile = Join-Path $root ".env.local"
if (-not $WebOnly -and -not (Test-Path $envFile)) {
  throw ".env.local not found at repo root. Fetch it from GitLab Secure Files first."
}
$py = Join-Path $root "apps\api\.venv\Scripts\python.exe"
if (-not $WebOnly -and -not (Test-Path $py)) {
  throw "apps\api\.venv missing. Run scripts\dev-windows-bootstrap.ps1 first."
}

function Import-DotEnv {
  param([string]$Path)

  # Load .env.local into the process environment. The api reads os.environ over
  # its ENV_FILE, so injected vars take effect without a repo-root .env.
  foreach ($raw in Get-Content $Path) {
    $t = $raw.Trim()
    if (-not $t -or $t.StartsWith('#') -or -not $t.Contains('=')) { continue }
    if ($t.StartsWith('export ')) { $t = $t.Substring(7).Trim() }
    $k = $t.Split('=', 2)[0].Trim()
    $v = $t.Substring($t.IndexOf('=') + 1).Trim()
    if ($v.Length -ge 2 -and $v[0] -eq $v[-1] -and ($v[0] -eq '"' -or $v[0] -eq "'")) { $v = $v.Substring(1, $v.Length - 2) }
    Set-Item -Path "env:$k" -Value $v
  }
}

if (Test-Path $envFile) {
  Import-DotEnv $envFile
} elseif ($WebOnly) {
  Write-Host ".env.local not found; continuing with existing web env and Vite defaults." -ForegroundColor Yellow
}

$apiProc = $null
if (-not $WebOnly) {
  # Local-dev safe defaults (match server dev): never auto-migrate the shared dev DB,
  # and don't gate startup on the LLM backend being reachable.
  $env:AI_DO_API_AUTO_MIGRATE = "0"
  $env:AI_DO_LLM_HEALTHCHECK_ON_STARTUP = "0"
  $env:AI_DO_LLM_REQUIRED = "0"
  Write-Host "==> api  http://127.0.0.1:8001/docs" -ForegroundColor Cyan
  $apiProc = Start-Process -PassThru -NoNewWindow -FilePath $py `
    -ArgumentList @("-m","uvicorn","ai_do_api.main:app","--app-dir","src","--host","127.0.0.1","--port","8001","--reload") `
    -WorkingDirectory (Join-Path $root "apps\api")
  if ($ApiOnly) {
    Write-Host "api pid $($apiProc.Id). Ctrl+C to stop." -ForegroundColor Green
    try {
      Wait-Process -Id $apiProc.Id
    }
    finally {
      if ($apiProc -and -not $apiProc.HasExited) {
        taskkill /PID $apiProc.Id /T /F 2>$null | Out-Null
      }
    }
    return
  }
}

try {
  Write-Host "==> web  http://localhost:4200" -ForegroundColor Cyan
  # Use `pnpm exec nx`, not `pnpm nx`: the root "nx" package script wraps nx in
  # the Unix `env -u ...` command, which does not exist on Windows.
  # NX_ISOLATE_PLUGINS=false runs nx plugins in-process; isolated plugin workers
  # fail their 5s socket handshake on Windows and stall the project graph.
  $env:NO_COLOR = $null; $env:NODE_ENV = $null
  $env:NX_DAEMON = "false"; $env:NX_ISOLATE_PLUGINS = "false"
  pnpm exec nx dev web
}
finally {
  if ($apiProc -and -not $apiProc.HasExited) {
    taskkill /PID $apiProc.Id /T /F 2>$null | Out-Null
  }
}
