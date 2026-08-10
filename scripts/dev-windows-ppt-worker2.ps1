<#
.SYNOPSIS
  Second Windows-native local PPT worker (node: ppt-local2). Same as
  dev-windows-ppt-worker.ps1 but a distinct -n so two solo workers can drain the
  `ppt_generate_dedicated` queue in parallel (internal Qwen generation is slow
  ~10min/job; one solo worker serializes the backlog). Temporary throughput aid.
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$envFile = Join-Path $root ".env.local"
if (-not (Test-Path $envFile)) { throw ".env.local not found at repo root." }
$py = Join-Path $root "apps\api\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "apps\api\.venv missing." }

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
$env:AI_DO_LLM_HEALTHCHECK_ON_STARTUP = "0"
$env:AI_DO_LLM_REQUIRED = "0"

Write-Host "==> ppt worker #2 (queue: ppt_generate_dedicated, node: ppt-local2)" -ForegroundColor Cyan
& $py -m celery -A ai_do_worker.celery_app:celery_app worker `
  -Q ppt_generate_dedicated `
  --pool=solo `
  --concurrency=1 `
  --without-mingle --without-gossip --without-heartbeat `
  -n ppt-local2@%h `
  --loglevel=info
