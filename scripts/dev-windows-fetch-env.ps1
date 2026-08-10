<#
.SYNOPSIS
  Install glab (if missing) and fetch .env.local from GitLab Secure Files into the repo root.

.DESCRIPTION
  - Skips when .env.local already exists (use -Force to overwrite).
  - Installs glab via winget if not on PATH; refreshes PATH from the registry so the
    same session can invoke it.
  - Configures the open-alm internal GitLab host (http on port 8929).
  - Authenticates: prefers GLAB_PAT or GITLAB_TOKEN from the environment (non-interactive,
    safe for tooling). Falls back to interactive `glab auth login` when neither is set.
  - Resolves the secure file by name (".env.local") and downloads it to the repo root.

  Token handling: never logged, never persisted by this script. glab stores its own
  credentials in the OS keyring when you use the interactive login. Do NOT type a PAT
  literal on the command line — it would land in PowerShell/PSReadLine history.

.PARAMETER Force
  Re-download even if .env.local already exists.

.EXAMPLE
  # Recommended for humans: prompts for the PAT securely via `glab auth login`,
  # so the token never touches the command line or shell history.
  powershell -ExecutionPolicy Bypass -File scripts\dev-windows-fetch-env.ps1

.EXAMPLE
  # CI / agent only: when GLAB_PAT (or GITLAB_TOKEN) is ALREADY injected as a
  # masked secret by the runner — never assigned by hand at an interactive prompt:
  powershell -ExecutionPolicy Bypass -File scripts\dev-windows-fetch-env.ps1
#>
param([switch]$Force)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$gitlabHost = "128.1.253.101:8929"
$repo = "open-alm/open-alm"
$envFile = Join-Path $root ".env.local"

if ((Test-Path $envFile) -and -not $Force) {
  Write-Host ".env.local already present at $envFile. Use -Force to overwrite." -ForegroundColor Yellow
  return
}

# Refresh PATH from the registry up front. winget-installed binaries (glab) only
# show up in already-running shells whose env block predates the install once we
# pull the current Machine+User PATH back in.
$env:Path = "$([Environment]::GetEnvironmentVariable('Path','Machine'));$([Environment]::GetEnvironmentVariable('Path','User'))"

# 1. Ensure glab is installed
if (-not (Get-Command glab -ErrorAction SilentlyContinue)) {
  Write-Host "==> Installing glab via winget" -ForegroundColor Cyan
  winget install --id GLab.GLab -e --accept-source-agreements --accept-package-agreements --disable-interactivity
  if ($LASTEXITCODE -ne 0) { throw "winget failed to install GLab.GLab (exit $LASTEXITCODE)" }
  # winget updates the registry PATH; re-refresh so the freshly installed glab is visible.
  $env:Path = "$([Environment]::GetEnvironmentVariable('Path','Machine'));$([Environment]::GetEnvironmentVariable('Path','User'))"
  if (-not (Get-Command glab -ErrorAction SilentlyContinue)) {
    throw "glab still not on PATH after install. Open a new shell and re-run."
  }
}

# 2. Configure glab to use HTTP on the internal host.
# Use --host, not -h: glab parses -h as --help here, so the setting silently no-ops
# and api calls would fall back to https against this http-only internal GitLab.
glab config set api_protocol http --host $gitlabHost | Out-Null
if ($LASTEXITCODE -ne 0) { throw "glab config set failed (exit $LASTEXITCODE)" }

# 3. Authenticate
$pat = $env:GLAB_PAT
if (-not $pat) { $pat = $env:GITLAB_TOKEN }
if ($pat) {
  # Non-interactive: glab reads GITLAB_TOKEN + GITLAB_HOST from the env.
  $env:GITLAB_HOST = $gitlabHost
  $env:GITLAB_TOKEN = $pat
  Write-Host "==> Auth via env var (non-interactive)" -ForegroundColor Cyan
} else {
  # Note: use --hostname, not -h. glab parses -h as --help for `auth status`.
  & glab auth status --hostname $gitlabHost 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) {
    Write-Host "==> Interactive login required. Paste an api-scope PAT when prompted." -ForegroundColor Cyan
    # Prompt for the PAT and pipe it via --stdin so it never lands on the command line
    # or in PSReadLine history. Store it in the OS keyring (--use-keyring) to match the
    # documented manual flow; only fall back to glab's config file if the keyring is
    # unavailable on this machine.
    $secure = Read-Host "GitLab PAT (api scope)" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
      $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
      $plain | glab auth login --hostname $gitlabHost --api-host $gitlabHost `
        --api-protocol http --git-protocol ssh --use-keyring --stdin
      if ($LASTEXITCODE -ne 0) {
        Write-Host "    keyring login failed; retrying with config-file storage." -ForegroundColor Yellow
        $plain | glab auth login --hostname $gitlabHost --api-host $gitlabHost `
          --api-protocol http --git-protocol ssh --stdin
        if ($LASTEXITCODE -ne 0) { throw "glab auth login failed" }
      }
    } finally {
      if ($bstr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
      Remove-Variable -Name plain, secure -ErrorAction SilentlyContinue
    }
  }
}

# 4. Resolve the .env.local secure file by name
Write-Host "==> Resolving secure file '.env.local' in $repo" -ForegroundColor Cyan
$projEnc = $repo -replace '/','%2F'
$listJson = & glab api "projects/$projEnc/secure_files?per_page=100"
if ($LASTEXITCODE -ne 0) { throw "glab api list failed (exit $LASTEXITCODE)" }
$files = $listJson | ConvertFrom-Json
$matches = @($files | Where-Object { $_.name -eq '.env.local' })
if ($matches.Count -eq 0) {
  $names = ($files | ForEach-Object { $_.name }) -join ', '
  throw "No secure file named '.env.local' in $repo. Available: $names"
}
if ($matches.Count -gt 1) {
  # Match the secure-env helper: refuse on duplicates rather than guess, so a stale
  # .env.local is never installed over the intended one.
  $ids = ($matches | ForEach-Object { $_.id }) -join ', '
  throw "Multiple secure files named '.env.local' in $repo (ids: $ids). Remove duplicates in GitLab first."
}
$match = $matches[0]
Write-Host "    found id=$($match.id) checksum=$($match.checksum)" -ForegroundColor DarkGray

# 5. Download to a temp file, then replace atomically. glab securefile download has no
# overwrite flag and errors if the target exists, so a -Force re-download must not point
# it at the live .env.local. Downloading aside first also keeps the existing file intact
# if the fetch fails midway.
$tmp = Join-Path $root ".env.local.download.tmp"
if (Test-Path $tmp) { Remove-Item -Path $tmp -Force }
try {
  glab securefile download $match.id --path $tmp -R $repo
  if ($LASTEXITCODE -ne 0) { throw "glab securefile download failed (exit $LASTEXITCODE)" }
  if (-not (Test-Path $tmp)) { throw "download reported success but $tmp is missing" }
  Move-Item -Path $tmp -Destination $envFile -Force
} finally {
  if (Test-Path $tmp) { Remove-Item -Path $tmp -Force }
}
Write-Host "==> .env.local saved to $envFile" -ForegroundColor Green
