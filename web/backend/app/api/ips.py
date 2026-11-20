"""IPS detection and mitigation endpoints.

Provides:
  * ``POST /api/v1/ips/detect`` - Run IDS model inference on flow features,
    return attack prediction and alert.
  * ``POST /api/v1/ips/mitigate`` - Generate a mitigation request from a
    detection result according to the current IPS mode (detection_only,
    manual_approval, automatic_blocking).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..services.sdn_adapter import DetectionResult, MitigationRequest as MR, MitigationMode as MM
from ..schemas import (
    PredictionRequest,
    PredictionStatusResponse,
    SDNStatusResponse,
)
from ..services.sdn_service import SDNService
from .deps import get_sdn


router = APIRouter(
    prefix="/ips",
    tags=["ips"],
    dependencies=[],
)


@router.post(
    "/detect",
    response_model=PredictionStatusResponse,
    summary="Run IDS model inference on flow features",
)
def ips_detect(
    payload: PredictionRequest,
    sdn_service: SDNService = Depends(get_sdn),
) -> PredictionStatusResponse:
    """Run the GRU IDS model on the provided 48-feature vector.

    Returns a ``PredictionStatusResponse`` containing the prediction probability
    and binary label.  If an alert is generated (attack predicted), the response
    includes it in the ``reason`` field for downstream consumption.
    """
    adapter = sdn_service._adapter
    try:
        # Use the adapter's detect pipeline; it reads flow stats internally.
        # Since we're receiving raw features via the payload, we'll map them
        # through the model directly using predict logic adapted from the adapter.
        import numpy as np
        from ..domain.model import keras_available, build_gru_model
        from ..domain.dataset import apply_scaler, ScalerStats

        FEATURE_NAME_COUNT = 48
        MODEL_INPUT_SHAPE = (1, 1, FEATURE_NAME_COUNT)

        if adapter.model is None:
            if keras_available():
                from ..services.sdn_adapter import create_sdn_adapter
                adapter = create_sdn_adapter(mode="mock")
                adapter.model = build_gru_model(input_features=FEATURE_NAME_COUNT)
            else:
                return PredictionStatusResponse(
                    available=False,
                    reason="IDS model not initialized and TensorFlow unavailable.",
                )

        features = payload.features
        if len(features) != FEATURE_NAME_COUNT:
            return PredictionStatusResponse(
                available=False,
                reason=f"Expected {FEATURE_NAME_COUNT} features, got {len(features)}.",
            )

        if adapter.scaler is not None:
            features_scaled = apply_scaler([features], adapter.scaler)[0]
        else:
            features_scaled = features

        X = np.array(features_scaled, dtype=np.float32).reshape(MODEL_INPUT_SHAPE)

        if not keras_available():
            return PredictionStatusResponse(
                available=False,
                reason="TensorFlow/Keras is not available for inference.",
            )

        pred = adapter.model.predict(X, verbose=0)[0][0]
        label = 1 if pred >= 0.5 else 0

        alert = None
        if label == 1:
            alert = {
                "type": "intrusion_detected",
                "flow_id": "api-ips-detect",
                "timestamp": __import__("time").time(),
                "prediction_probability": float(pred),
                "features_used": features,
            }

        # Record the detection result in adapter history
        result_dict = {
            "flow_id": "api-ips-detect",
            "timestamp": __import__("time").time(),
            "prediction": float(pred),
            "label": int(label),
            "features": features,
            "switch_dp_id": getattr(getattr(adapter, "_switch_info", None), "dp_id", "unknown"),
            "table_id": 0,
            "alert": alert,
        }
        try:
            from ..services.sdn_adapter import DetectionResult
            detection_result = DetectionResult(
                flow_id=result_dict["flow_id"],
                timestamp=result_dict["timestamp"],
                prediction=result_dict["prediction"],
                label=result_dict["label"],
                features=result_dict["features"],
                switch_dp_id=result_dict["switch_dp_id"],
                table_id=result_dict["table_id"],
                alert=result_dict.get("alert"),
            )
            adapter.record_result(detection_result)
        except Exception:
            pass

        reason_parts = [f"prediction={float(pred):.4f}"]
        if alert is not None:
            reason_parts.append(f"alert={alert['type']}")

        return PredictionStatusResponse(
            available=True,
            reason=" ".join(reason_parts),
            model="keras_gru",
            preprocessing="securefed-preprocessing-v1",
        )

    except Exception as exc:
        return PredictionStatusResponse(
            available=False,
            reason=f"Inference failed: {exc}",
        )


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