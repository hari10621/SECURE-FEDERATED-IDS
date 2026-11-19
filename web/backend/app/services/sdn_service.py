"""SDN/IPS boundary stub.

No controller integration, OpenFlow rule, or mitigation action exists in
Phase 3. The service exposes status only and refuses actions.
"""

from __future__ import annotations

from typing import Any

from ..errors import UnavailableError


class SDNService:
    def status(self) -> dict[str, Any]:
        return {
            "available": False,
            "reason": "SDN/IPS integration is not implemented in Phase 3.",
        }

    def apply_mitigation(self, *_args: Any, **_kwargs: Any) -> None:
        raise UnavailableError("SDN mitigation is unavailable in Phase 3")
