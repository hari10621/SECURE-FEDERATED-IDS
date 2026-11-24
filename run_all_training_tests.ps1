$env:SECUREFED_ENABLE_TRAINING="true"
$env:SECUREFED_ENABLE_PREDICTIONS="true"
$env:SECUREFED_ENABLE_CKKS="1"
$env:SECUREFED_RUN_TF_TESTS="1"

& python -m pytest "web/backend/tests/test_training_api.py" -v 2>&1