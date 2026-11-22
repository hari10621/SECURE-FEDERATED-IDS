from pathlib import Path
import sys

backend_dir = Path(__file__).resolve().parent / "web" / "backend"
sys.path.insert(0, str(backend_dir))

from app.schemas import ExperimentCreate

# Test that client_count=2 is accepted
exp2 = ExperimentCreate(name="2-Client Exp", dataset_id="dataset_001", client_count=2)
print(f"ExperimentCreate with client_count=2: OK - {exp2.name}, client_count={exp2.client_count}")

# Test that client_count=3 is accepted
exp3 = ExperimentCreate(name="3-Client Exp", dataset_id="dataset_001", client_count=3)
print(f"ExperimentCreate with client_count=3: OK - {exp3.name}, client_count={exp3.client_count}")

# Test that invalid count still fails
try:
    exp5 = ExperimentCreate(name="5-Client Exp", dataset_id="dataset_001", client_count=5)
    print("ERROR: client_count=5 should have been rejected")
except ValueError as e:
    print(f"client_count=5 correctly rejected: {e}")
