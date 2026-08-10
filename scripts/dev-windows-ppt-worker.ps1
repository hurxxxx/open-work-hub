<#
.SYNOPSIS
  Windows-native local PPT worker: consumes the `ppt_generate_dedicated` Celery
  queue against the shared dev broker, running CURRENT local code for
  ppt_generator.generate / chat_edit / finalize. (Queue name is dedicated so the
  remote long worker — which still subscribes to the legacy `ppt_generate` — can
  never steal these jobs and run stale code.)

.DESCRIPTION
  - Loads repo-root .env.local into the process environment (same as
    dev-windows.ps1) so DB/broker/MinIO/LLM settings are available.
  - Uses the api venv python (which has celery + python-pptx + the worker deps).
    Does NOT use `uv run` (avoids the y-py rebuild that fails on Windows).
  - Starts the full open_alm_worker celery app but listens ONLY on
    `ppt_generate_dedicated`, so PPT 변환/생성 요청을 이 PC 의 최신 코드로 처리한다.
  - --without-mingle/gossip/heartbeat: 공유 브로커에 다른 워커가 떠 있을 때
    solo 워커가 mingle/gossip 단계에서 hang 되는 것을 막는다.

  Start this alongside scripts\dev-windows.ps1 (api+web).
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$envFile = Join-Path $root ".env.local"
if (-not (Test-Path $envFile)) {
  throw ".env.local not found at repo root. Fetch it from GitLab Secure Files first."
}
$py = Join-Path $root "apps\api\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
  throw "apps\api\.venv missing. Run scripts\dev-windows-bootstrap.ps1 first."
}

foreach ($raw in Get-Content $envFile) {
  $t = $raw.Trim()
  if (-not $t -or $t.StartsWith('#') -or -not $t.Contains('=')) { continue }
  if ($t.StartsWith('export ')) { $t = $t.Substring(7).Trim() }
  $k = $t.Split('=', 2)[0].Trim()
  $v = $t.Substring($t.IndexOf('=') + 1).Trim()
  if ($v.Length -ge 2 -and $v[0] -eq $v[-1] -and ($v[0] -eq '"' -or $v[0] -eq "'")) { $v = $v.Substring(1, $v.Length - 2) }
  Set-Item -Path "env:$k" -Value $v
}

$env:PYTHONPATH = "$root\apps\worker\src;$root\apps\api\src"
# Local-dev safe defaults: don't gate worker startup on LLM reachability.
$env:OPEN_ALM_LLM_HEALTHCHECK_ON_STARTUP = "0"
$env:OPEN_ALM_LLM_REQUIRED = "0"

Write-Host "==> ppt worker (queue: ppt_generate_dedicated)  broker: $env:OPEN_ALM_WORKER_BROKER_URL" -ForegroundColor Cyan
& $py -m celery -A open_alm_worker.celery_app:celery_app worker `
  -Q ppt_generate_dedicated `
  --pool=solo `
  --concurrency=1 `
  --without-mingle --without-gossip --without-heartbeat `
  -n ppt-local@%h `
  --loglevel=info
