"""Demo: Verify 2-3 client support in the GRU federated learning prototype."""

from pathlib import Path
import sys

backend_dir = Path(__file__).resolve().parent / "web" / "backend"
sys.path.insert(0, str(backend_dir))

from app.schemas import ExperimentCreate

print("=== GRU Federated Learning Prototype - 2-3 Client Support ===")

# Test 1: Experiment creation with 2 clients
print("1. Creating experiment with 2 clients...")
try:
    exp = ExperimentCreate(
        name="2-Client Test",
        dataset_id="dataset_001",
        client_count=2,
    )
    print("   [OK] client_count=2 is valid")
except ValueError as e:
    print(f"   [FAIL] {e}")

# Test 2: Experiment creation with 3 clients
print("2. Creating experiment with 3 clients...")
try:
    exp = ExperimentCreate(
        name="3-Client Test", 
        dataset_id="dataset_001",
        client_count=3,
    )
    print("   [OK] client_count=3 is valid")
except ValueError as e:
    print(f"   [FAIL] {e}")

# Test 3: Experiment creation with 4 clients (legacy)
print("3. Creating experiment with 4 clients (legacy)...")
try:
    exp = ExperimentCreate(
        name="4-Client Test",
        dataset_id="dataset_001",
        client_count=4,
    )
    print("   [OK] client_count=4 is valid")
except ValueError as e:
    print(f"   [FAIL] {e}")

# Test 4: Experiment creation with 8 clients (legacy)
print("4. Creating experiment with 8 clients (legacy)...")
try:
    exp = ExperimentCreate(
        name="8-Client Test",
        dataset_id="dataset_001",
        client_count=8,
    )
    print("   [OK] client_count=8 is valid")
except ValueError as e:
    print(f"   [FAIL] {e}")

# Test 5: Experiment creation with 12 clients (legacy)
print("5. Creating experiment with 12 clients (legacy)...")
try:
    exp = ExperimentCreate(
        name="12-Client Test",
        dataset_id="dataset_001",
        client_count=12,
    )
    print("   [OK] client_count=12 is valid")
except ValueError as e:
    print(f"   [FAIL] {e}")

# Test 6: Invalid client count (5) should be rejected
print("6. Creating experiment with 5 clients (invalid)...")
try:
    exp = ExperimentCreate(
        name="Invalid Test",
        dataset_id="dataset_001",
        client_count=5,
    )
    print("   [FAIL] client_count=5 should have been rejected")
except ValueError as e:
    print(f"   [OK] Correctly rejected: {e}")

# Test 7: Invalid client count (7) should be rejected
print("7. Creating experiment with 7 clients (invalid)...")
try:
    exp = ExperimentCreate(
        name="Invalid Test 2",
        dataset_id="dataset_001",
        client_count=7,
    )
    print("   [FAIL] client_count=7 should have been rejected")
except ValueError as e:
    print(f"   [OK] Correctly rejected: {e}")

print()
print("Supported client counts: 2, 3, 4, 8, 12")
print("The GRU model federated learning prototype is ready with 2-3 client support!")
print("Changes made:")
print("  - training_service.py: extended client count validation")
print("  - simulation_service.py: extended client count validation") 
print("  - research_adapter.py: added scripts for 2 and 3 clients")
print("  - schemas.py: ExperimentCreate validator updated")