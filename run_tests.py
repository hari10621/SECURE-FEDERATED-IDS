import subprocess
result = subprocess.run(["python", "-m", "pytest", "-q"], cwd=r"C:\Users\HARIS\Desktop\SecureFed-IDS\web/backend/tests", capture_output=True, text=True)
print("STDOUT:")
print(result.stdout)
print("\nSTDERR:")
print(result.stderr)
print("\nReturn code:", result.returncode)