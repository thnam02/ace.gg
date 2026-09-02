from __future__ import annotations

from app.metrics.cir_validation_config import CIR_ROLES
from app.schemas.cir_ranking import RoleMix

CANONICAL_ROLES = set(CIR_ROLES)
SECONDARY_ROLE_MIN_SHARE = 0.10


def build_role_mix(
    counts: dict[str, int],
    main_role: str | None,
) -> list[RoleMix]:
    """Round-weighted roles a player actually played. CIR `main_role` stays highlighted."""
    cleaned: dict[str, int] = {}
    for raw_name, rounds in counts.items():
        name = raw_name.strip()
        if name not in CANONICAL_ROLES or rounds <= 0:
            continue
        cleaned[name] = cleaned.get(name, 0) + rounds
    total = sum(cleaned.values())
    main = main_role.strip() if main_role and main_role.strip() else None
    if main and main not in CANONICAL_ROLES:
        main = None

    items: list[RoleMix] = []
    for role, rounds in cleaned.items():
        share = rounds / total if total else 0.0
        is_main = main is not None and role.lower() == main.lower()
        if not is_main and share < SECONDARY_ROLE_MIN_SHARE:
            continue
        items.append(RoleMix(role=role, rounds=rounds, share=share, is_main=is_main))

    if main and not any(item.is_main for item in items):
        main_rounds = cleaned.get(main, 0)
        items.insert(
            0,
            RoleMix(
                role=main,
                rounds=main_rounds,
                share=(main_rounds / total) if total else 0.0,
                is_main=True,
            ),
        )

    items.sort(key=lambda item: (not item.is_main, -item.rounds, item.role))
    return items
