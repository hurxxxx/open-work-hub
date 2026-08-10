<#
.SYNOPSIS
  Windows-native local industry-report worker: consumes ONLY the dedicated
  `news` Celery queue (shared by industry_report) against the shared dev broker
  and runs industry_report.collect_all.

.DESCRIPTION
  - Loads repo-root .env.local into the process environment (same as
    dev-windows.ps1) so DB/broker/MinIO settings are available.
  - Runs scripts\industry_report_local_worker.py with the api venv python
    (which has celery + httpx + bs4 + minio + sqlalchemy installed). Does NOT
    use `uv run` (avoids the y-py rebuild that fails on Windows).
  - Consumes only the `news` queue, so it never picks up other developers'
    shared default-queue tasks.

  Set OPEN_ALM_INDUSTRY_REPORT_CRAWL_ENABLED=1 to let collection actually run
  (otherwise the task returns "disabled", mirroring production).

  Set IR_LOCAL_BEAT_SECONDS to a positive number (e.g. 60) to enable an embedded
  beat at that interval for local verification; leave unset to run the worker
  only and trigger via the "데이터 수집" button / POST /industry-report/fetch.
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

Write-Host "==> industry-report worker (queue: news)  broker: $env:OPEN_ALM_WORKER_BROKER_URL" -ForegroundColor Cyan
& $py (Join-Path $root "scripts\industry_report_local_worker.py")
