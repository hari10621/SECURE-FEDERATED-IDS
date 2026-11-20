# SecureFed-IDS — REST API Documentation

The SecureFed-IDS backend provides a RESTful JSON API running on port 8000. All routes are prefixed with `/api/v1`. Interactive OpenAPI Swagger documentation is available at `http://127.0.0.1:8000/docs`.

---

## 1. Authentication & Common Headers

- **Bearer Authentication (Optional):** When `SECUREFED_API_TOKEN` is configured, requests must supply the header:
  ```http
  Authorization: Bearer <your_token>
  ```
- **Request Tracing:** All responses include an `X-Request-ID` header containing a UUID or sanitized client-supplied ID.
- **Error Response Format:**
  ```json
  {
    "error": {
      "code": "input_validation_error",
      "message": "Field 'rounds' must be positive",
      "details": null
    }
  }
  ```

---

## 2. Health & System Endpoints

### `GET /api/v1/health`
Returns system component health and timestamp.
```json
{
  "status": "ok",
  "version": "0.1.0",
  "database": "ok",
  "encryption": "unavailable",
  "timestamp": "2026-11-20T03:09:48.433299Z"
}
```

### `GET /api/v1/version`
Returns software versions and runtime environment.
```json
{
  "name": "SecureFed-IDS API",
  "version": "0.1.0",
  "api_version": "v1",
  "environment": "local",
  "python_version": "3.11.17"
}
```

### `GET /api/v1/encryption/status`
Returns homomorphic encryption backend availability.
```json
{
  "available": false,
  "mode": "unavailable",
  "reason": "Native true_threshold_ckks extension is not installed or verified",
  "encryption_claimed": false
}
```

### `GET /api/v1/sdn/status`
Returns SDN controller connection and switch topology.
```json
{
  "available": true,
  "reason": "",
  "mode": "mock",
  "switch": {
    "dp_id": "00:00:00:00:00:00:00:01",
    "mac": "00:00:00:00:00:00",
    "ip": "10.0.0.1",
    "n_ports": 4
  }
}
```

---

## 3. Dataset Endpoints

### `POST /api/v1/datasets`
Uploads and validates a network traffic CSV.
- **Payload:** `multipart/form-data` with `file`, `name`, `label_column`, and `description`.
- **Response (`201 Created`):**
  ```json
  {
    "id": "e4b1c2d3...",
    "name": "InSDN_48Features",
    "feature_count": 48,
    "row_count": 5000,
    "validation_status": "valid",
    "research_compatible": true,
    "created_at": "2026-11-20T03:15:00Z"
  }
  ```

### `GET /api/v1/datasets`
Lists all uploaded datasets.

### `GET /api/v1/datasets/{id}`
Retrieves detailed metadata for a specific dataset.

---

## 4. Experiment Endpoints

### `POST /api/v1/experiments`
Creates a new federated experiment configuration.
- **Request Body:**
  ```json
  {
    "name": "InSDN_15Rounds_4Clients",
    "dataset_id": "e4b1c2d3...",
    "client_count": 4,
    "description": "4-client federated GRU experiment"
  }
  ```

### `GET /api/v1/experiments`
Lists registered experiments.

### `GET /api/v1/experiments/{id}`
Retrieves experiment state, participating clients, and latest job results.

### `GET /api/v1/experiments/{id}/status`
Checks experiment readiness for simulation and GRU training.

---

## 5. Federated Execution Endpoints

### `POST /api/v1/experiments/{id}/simulate`
Spawns a fast in-process simulation using the reference linear model.
- **Request Body:**
  ```json
  {
    "mode": "clean",
    "rounds": 5,
    "local_epochs": 1,
    "batch_size": 32,
    "learning_rate": 0.0001,
    "seed": 42
  }
  ```
- **Response (`200 OK`):** Returns queued `Job` object.

### `POST /api/v1/experiments/{id}/train`
Spawns genuine 3-block Keras GRU federated learning training.
- **Request Body:**
  ```json
  {
    "mode": "clean",
    "rounds": 15,
    "local_epochs": 5,
    "batch_size": 32,
    "learning_rate": 0.0001,
    "weighting": "sample",
    "seed": 42
  }
  ```
- **Response (`200 OK`):** Returns queued `Job` object.

---

## 6. Job & Artifact Endpoints

### `GET /api/v1/jobs/{id}`
Polls job execution progress and final metrics.
```json
{
  "id": "78c8699a...",
  "job_type": "training_run",
  "status": "succeeded",
  "progress": 1.0,
  "message": "federated GRU training complete",
  "final_metrics": {
    "accuracy": 0.9994,
    "precision": 0.9992,
    "recall": 0.9996,
    "f1": 0.9994,
    "loss": 0.0032
  }
}
```

### `POST /api/v1/jobs/{id}/cancel`
Requests graceful cancellation of a running background job.

---

## 7. Prediction & Inference Endpoints

### `GET /api/v1/predictions/status`
Checks if an active trained model artifact is loaded for live inference.

### `POST /api/v1/predictions`
Performs real-time IDS classification on a 48-feature flow vector.
- **Request Body:**
  ```json
  {
    "features": [0.05, 0.0, 0.0, 10.0, 0.012, ...]
  }
  ```
- **Response (`200 OK`):**
  ```json
  {
    "prediction": 0.984,
    "label": 1,
    "classification": "attack",
    "timestamp": 1795143727.0
  }
  ```
