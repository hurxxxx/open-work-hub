$env:AI_DO_PROD_ROOT = "/projects/ai-do/prod"
bash scripts/prod-systemd.sh restart
Write-Host "http://127.0.0.1:8000/healthz"

