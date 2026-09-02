from __future__ import annotations

from app.metrics.mir.mir_config import CIR_TO_MIR_COMBAT


def alias_context_features(cir_features: dict[str, float | None]) -> dict[str, float | None]:
    """Map CIR context-residual names onto MIR vocabulary without copying combat twice."""
    aliased: dict[str, float | None] = dict(cir_features)
    for cir_name, mir_name in CIR_TO_MIR_COMBAT.items():
        if cir_name in cir_features:
            aliased[mir_name] = cir_features[cir_name]
    return aliased


def opening_attempts(first_kills: int, first_deaths: int) -> int:
    return max(0, int(first_kills) + int(first_deaths))
