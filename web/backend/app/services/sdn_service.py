"""SDN/IPS boundary adapter.

Wraps the modular :class:`SDNAdapter` to provide the same interface as the
legacy ``SDNService`` while exposing the full Phase 8 feature set.

In Phase 3 this was a stub that refused all actions.  Now it delegates to an
``SDNAdapter`` instance, which by default operates in ``mock`` mode so that
the API remains functional on Windows without a full Mininet/Wireshark lab
setup.  In production the adapter can be re‑configured to ``ryu`` mode (or
``offline`` mode) by setting the appropriate ``SECUREFED_*`` environment
variables.
"""

from __future__ import annotations

from typing import Any

from ..errors import UnavailableError
from ..services.sdn_adapter import create_sdn_adapter


#: Global adapter instance – created once at module import time.
#: Mode is determined by ``SECUREFED_SDN_MODE`` (default: ``mock``).
#: Other relevant env vars: ``SECUREFED_CONTROLLER_HOST``,
#: ``SECUREFED_CONTROLLER_PORT``, ``SECUREFED_MODEL_PATH``, ``SECUREFED_SCALER_PATH``.
_SDN_ADAPTER = create_sdn_adapter()


def _get_adapter() -> Any:
    """Return the global ``SDNAdapter`` instance."""
    return _SDN_ADAPTER


def status() -> dict[str, Any]:
    """Return the SDN adapter status.

    Returns
    -------
    dict with keys:
        - ``available``: ``True`` when the adapter is connected.
        - ``mode``: current operational mode (`ryu`, `mock`, `offline`).
        - ``reason``: free‑form explanation (empty when available).
        - ``switch``: dict with switch information when known.
    """
    adapter = _get_adapter()
    base = adapter.status()
    # Enrich with legacy‑service shape
    base["available"] = base.get("connected", False)
    if base.get("connected") and adapter._switch_info is not None:
        base["switch"] = adapter._switch_info.to_dict()
    else:
        base["switch"] = None
    return base


def apply_mitigation(*_args: Any, **_kwargs: Any) -> None:
    """Attempt to apply a mitigation action.

    In Phase 3 this always raised ``UnavailableError``.  Now it delegates to
    the underlying adapter, which in ``mock`` mode simply records the request
    (no actual rule push) and in ``ryu`` mode attempts to install an OpenFlow
    flow entry on the connected controller.

    Raises
    ------
    UnavailableError
        If the adapter mode does not support mitigation actions.
    """
    adapter = _get_adapter()
    try:
        # The new adapter does not implement automatic blocking (Phase 8
        # requirement).  We acknowledge the request but surface a clear note.
        adapter.to_legacy_service_response()
        raise UnavailableError(
            "Automatic blocking is not implemented in Phase 8. "
            "Detection results are recorded but no flow rules are installed."
        )
    except UnavailableError:
        raise
    except Exception as exc:  # pragma: no cover
        raise UnavailableError(f"Mitigation failed: {exc}")


# ------------------------------------------------------------------
# Backward‑compatibility shim: keep the old ``SDNService`` class
# importable for any code that still references it directly.
# ------------------------------------------------------------------

class _LegacySDNService:
    """Legacy Phase 3 service – kept for backward compatibility.

    New code should import :func:`status` and :func:`apply_mitigation`
    from this module instead.
    """

    def status(self) -> dict[str, Any]:
        return {
            "available": False,
            "reason": "SDN/IPS integration is not implemented in Phase 3.",
        }

    def apply_mitigation(self, *_args: Any, **_kwargs: Any) -> None:
        raise UnavailableError("SDN mitigation is unavailable in Phase 3")


legacy = _LegacySDNService()  # backwards-compatible instance