from __future__ import annotations

from app.metrics.cir.config import COMBAT_WEIGHT, VALIDATED_PC1_LOADINGS


def equal_weight_combat_factor(z_kpr: float, z_negative_dpr: float) -> float:
    """Public CombatFactor. Ranking-equivalent to validated PC1 up to a constant scale."""
    return COMBAT_WEIGHT * float(z_kpr) + COMBAT_WEIGHT * float(z_negative_dpr)


def pca_equivalent_pc1(z_kpr: float, z_negative_dpr: float) -> float:
    return VALIDATED_PC1_LOADINGS[0] * float(z_kpr) + VALIDATED_PC1_LOADINGS[1] * float(
        z_negative_dpr
    )


def combat_factor_metadata() -> dict[str, object]:
    return {
        "combat_factor_type": "equal_weight_standardized",
        "pca_equivalent": True,
        "validated_pc1_loadings": list(VALIDATED_PC1_LOADINGS),
        "public_form": "0.5 * z_kpr + 0.5 * z_negative_dpr",
        "pc1_form": "1/sqrt(2) * z_kpr + 1/sqrt(2) * z_negative_dpr",
    }
