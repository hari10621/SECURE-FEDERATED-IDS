"""IPS detection and mitigation endpoints.

Provides:
  * ``POST /api/v1/ips/detect`` - Run IDS model inference on flow features,
    return attack prediction and alert.
  * ``POST /api/v1/ips/mitigate`` - Generate a mitigation request from a
    detection result according to the current IPS mode (detection_only,
    manual_approval, automatic_blocking).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..services.sdn_adapter import DetectionResult, MitigationRequest as MR, MitigationMode as MM
from ..schemas import (
    PredictionRequest,
    PredictionStatusResponse,
    SDNStatusResponse,
)
from ..services.sdn_service import SDNService
from ..errors import UnavailableError
from ..services.model_service import ModelService
from .deps import get_models, get_sdn, require_auth


router = APIRouter(
    prefix="/ips",
    tags=["ips"],
    dependencies=[Depends(require_auth)],
)


@router.post(
    "/detect",
    response_model=PredictionStatusResponse,
    summary="Run IDS model inference on flow features",
)
def ips_detect(
    payload: PredictionRequest,
    sdn_service: SDNService = Depends(get_sdn),
    models: ModelService = Depends(get_models),
) -> PredictionStatusResponse:
    """Score submitted flow statistics with the admitted model and fitted scaler."""
    import time

    try:
        prediction = models.predict(payload.features)
    except UnavailableError as exc:
        return PredictionStatusResponse(available=False, reason=str(exc))
    probability = prediction["prediction"]
    label = prediction["label"]
    alert = {"type": "intrusion_detected", "prediction_probability": probability} if label else None
    sdn_service._adapter.record_result(DetectionResult(
        flow_id="api-ips-detect", timestamp=time.time(), prediction=probability,
        label=label, features=payload.features, switch_dp_id="unknown", table_id=0, alert=alert,
    ))
    reason = f"prediction={probability:.4f}" + (" alert=intrusion_detected" if label else "")
    return PredictionStatusResponse(available=True, reason=reason, model="keras_gru",
                                    preprocessing="securefed-preprocessing-v1")


@router.post(
    "/mitigate",
    response_model=dict[str, Any],
    summary="Generate IPS mitigation request from detection result",
)
def ips_mitigate(
    payload: dict[str, Any],
    sdn_service: SDNService = Depends(get_sdn),
) -> dict[str, Any]:
    """Generate a mitigation request from a detection result.

    The ``payload`` should contain the keys from a ``DetectionResult`` (or
    the ``reason`` field from ``/ips/detect``).  The resulting mitigation
    request is processed according to the current ``SDNAdapter.ips_mode``:

    - ``detection_only``  (default): Record the request, no OpenFlow rules
      installed.
    - ``manual_approval``: Generate a request awaiting operator approval.
    - ``automatic_blocking``: Attempt to install an OpenFlow rule (mock mode
      installs a synthetic rule; ryu/offline modes may raise).

    Returns a dict with the ``mitigation_request`` and ``adapter_status``.
    """
    adapter = sdn_service._adapter
    try:
        # Extract detection result info from payload
        prediction = payload.get("prediction", 0.0)
        label = payload.get("label", 0)
        features = payload.get("features", [])
        switch_dp_id = payload.get("switch_dp_id", "00:00:00:00:00:00:00:01")
        table_id = payload.get("table_id", 0)

        # Build a DetectionResult mimicking the pipeline output
        from datetime import datetime
        import time as _time

        detection_result = DetectionResult(
            flow_id=payload.get("flow_id", f"{switch_dp_id}-{table_id}"),
            timestamp=_time.time(),
            prediction=float(prediction),
            label=int(label),
            features=(features if features else [0.0] * 48),
            switch_dp_id=switch_dp_id,
            table_id=table_id,
            alert=payload.get("alert"),
        )

        # Record detection if not already present
        adapter.record_result(detection_result)

        # Generate mitigation request
        request = adapter.request_mitigation(detection_result)

        # Build response
        response: dict[str, Any] = {
            "mitigation_request": request.to_dict(),
            "adapter_status": adapter.status(),
            "ips_mode": adapter.ips_mode,
            "summary": adapter.get_mitigation_summary(),
        }

        return response

    except Exception as exc:
        return {"error": str(exc), "status": "failed"}