cd C:\Users\HARIS\Desktop\SecureFed-IDS\web\backend
$env:SECUREFED_ENABLE_TRAINING="true"
$env:SECUREFED_ENABLE_PREDICTIONS="true"
$env:SECUREFED_ENABLE_CKKS="1"
. .venv-tf\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000