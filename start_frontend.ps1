cd C:\Users\HARIS\Desktop\SecureFed-IDS\web\frontend
$env:SECUREFED_ENABLE_TRAINING="true"
$env:SECUREFED_ENABLE_PREDICTIONS="true"
$env:SECUREFED_ENABLE_CKKS="1"
npm run dev -- --host 127.0.0.1 --port 5173