$env:OPEN_ALM_PROD_ROOT = "/projects/open-alm/prod"
bash scripts/prod-systemd.sh restart
Write-Host "http://127.0.0.1:8000/healthz"

