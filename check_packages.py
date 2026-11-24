import sys
sys.path.insert(0, r'web/backend/.venv-tf')
import os
packages_dir = os.path.join(os.path.dirname(os.path.dirname(r'web/backend/.venv-tf')), 'Lib', 'site-packages')
print("site-packages:", packages_dir if os.path.exists(packages_dir) else "not found")
if os.path.exists(packages_dir):
    pkgs = os.listdir(packages_dir)
    print("Packages:", pkgs[:20])
    for pkg in ['sklearn', 'scipy', 'imblearn', 'pandas', 'numpy']:
        if pkg in pkgs:
            print(f"{pkg}: FOUND")
        else:
            print(f"{pkg}: NOT FOUND")