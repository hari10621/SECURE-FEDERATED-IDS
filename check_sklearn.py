import sys
sys.path.insert(0, r'web/backend/.venv-tf')
import subprocess
result = subprocess.run([r'web/backend/.venv-tf/python', '-c', 'import sklearn; print("sklearn", sklearn.__version__)'], capture_output=True, text=True)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)