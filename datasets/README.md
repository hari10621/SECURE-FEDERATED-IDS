# SecureFed-IDS Datasets

This folder contains pre-generated, lightweight, research-compatible Intrusion Detection System (IDS) datasets and the generation script for the SecureFed-IDS platform.

---

## 1. Available Datasets

| File | Rows | File Size | Recommended Use Case |
| :--- | :--- | :--- | :--- |
| `insdn_compact_1k.csv` | 1,000 | **~548 KB** | Fast smoke testing, schema validation, quick debugging |
| `insdn_sdn_ids_5k.csv` | 5,000 | **~2.68 MB** | Standard federated training (matches default `training_max_rows=5000`) |
| `cicids_sdn_ids_12k.csv` | 12,000 | **~6.42 MB** | Multi-round / multi-client federated training (2, 3, 4, 8, 12 clients) |

---

## 2. Dataset Schema & Format

Every dataset strictly complies with the SecureFed-IDS schema:
- **Feature Count:** Exactly 48 numerical network flow features (Flow duration, packet rates, byte rates, TCP flags, TTL, protocol numbers, OpenFlow port statistics).
- **Label Column:** The 49th column is named `Label`.
- **Binary Classification:**
  - `0`: Normal / benign network traffic.
  - `1`: Intrusion / malicious attack traffic (DDoS, PortScan, SYN floods, brute force).
- **Validation Status:** Passes `validate_csv_file` with `valid=True` and `research_compatible=True`.

---

## 3. How to Upload & Use

### Via Web Console UI:
1. Start the SecureFed-IDS backend and frontend.
2. Navigate to `http://127.0.0.1:5173/datasets`.
3. Click **Upload Dataset**, select any `.csv` file from this `datasets/` directory, set the name, and confirm upload.
4. Go to `/training` to create an experiment using the uploaded dataset and start simulation or GRU training.

### Via API / curl:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/datasets" \
  -F "file=@datasets/insdn_sdn_ids_5k.csv;type=text/csv" \
  -F "name=InSDN 5K Dataset" \
  -F "dataset_type=insdn" \
  -F "label_column=Label"
```

---

## 4. Regenerating or Customizing Datasets

Run the Python generator script:
```bash
python datasets/generate_datasets.py
```
To generate a custom number of rows, import `generate_dataset`:
```python
from pathlib import Path
from datasets.generate_datasets import generate_dataset

generate_dataset(Path("custom_dataset.csv"), num_rows=25000)
```
