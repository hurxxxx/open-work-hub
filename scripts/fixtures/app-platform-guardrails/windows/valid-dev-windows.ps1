$env:OPEN_ALM_API_AUTO_MIGRATE = "0"
Write-Host "==> api http://127.0.0.1:8001/docs"
pnpm exec nx dev web

