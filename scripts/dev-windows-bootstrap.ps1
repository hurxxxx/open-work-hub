<#
.SYNOPSIS
  One-time Windows-native setup for AI-DO local development (no WSL).

.DESCRIPTION
  Installs JS + Python dependencies and builds the y-py CRDT extension, which
  has no upstream cp312 Windows wheel and must be compiled locally.

  Prerequisites (install manually if missing):
    - Node.js (LTS), pnpm 10.x   (corepack: `npm i -g pnpm@10.33.0`)
    - uv (Astral)                (`winget install astral-sh.uv`)
    - Rust + MSVC toolchain      (`winget install Rustlang.Rustup`)
    - VS Build Tools / C++ build tools (Windows SDK + MSVC linker)
      (`winget install Microsoft.VisualStudio.2022.BuildTools` with the
       "Desktop development with C++" workload)

  After bootstrap: authenticate glab and download the dev `.env.local` from GitLab
  Secure Files as described in docs\reference\setup-windows.md, then run
  scripts\dev-windows.ps1.
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "==> pnpm install" -ForegroundColor Cyan
pnpm install --frozen-lockfile

Write-Host "==> uv sync (apps/api, single venv; y-py installed separately)" -ForegroundColor Cyan
Push-Location (Join-Path $root "apps\api")
try { uv sync --python 3.12 --no-install-package y-py } finally { Pop-Location }

$py = Join-Path $root "apps\api\.venv\Scripts\python.exe"

& $py -c "import y_py" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "==> Building y-py 0.6.2 wheel (Rust + MSVC required)" -ForegroundColor Cyan
  $build = Join-Path $root ".dev\ypy-build"
  $wheelhouse = Join-Path $root ".dev\wheelhouse"
  New-Item -ItemType Directory -Force -Path $build, $wheelhouse | Out-Null

  $meta = Invoke-RestMethod "https://pypi.org/pypi/y-py/0.6.2/json"
  $sdist = $meta.urls | Where-Object { $_.packagetype -eq 'sdist' } | Select-Object -First 1
  $tar = Join-Path $build $sdist.filename
  Invoke-WebRequest $sdist.url -OutFile $tar -UseBasicParsing
  tar -xzf $tar -C $build

  # The 0.6.2 sdist's [project] table omits version/dynamic, which modern build
  # frontends reject. maturin reads the version from Cargo.toml once we mark it dynamic.
  $src = Join-Path $build "y_py-0.6.2"
  $pp = Join-Path $src "pyproject.toml"
  $c = Get-Content $pp -Raw
  if ($c -notmatch 'dynamic\s*=') {
    ($c -replace '(?m)^(name = "y-py")', "`$1`r`ndynamic = [`"version`"]") | Set-Content $pp -Encoding utf8
  }

  Push-Location $src
  try { uvx --from "maturin>=1.2.3,<2" maturin build --release -i $py -o $wheelhouse }
  finally { Pop-Location }

  $wheel = Get-ChildItem $wheelhouse -Filter "y_py-0.6.2-cp312-*win_amd64.whl" | Select-Object -First 1
  if (-not $wheel) { throw "y-py wheel build produced no cp312 win_amd64 wheel" }
  uv pip install --python $py $wheel.FullName
}

& $py -c "import y_py; print('y-py', y_py.__version__, 'OK')"
Write-Host "`nBootstrap complete. Next: download .env.local per docs\reference\setup-windows.md, then run scripts\dev-windows.ps1" -ForegroundColor Green
