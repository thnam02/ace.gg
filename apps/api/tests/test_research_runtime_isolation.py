from __future__ import annotations

from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PATHS = [
    API_ROOT / "app" / "main.py",
    API_ROOT / "app" / "api",
]


FORBIDDEN_IMPORT_TOKENS = (
    "mir_experiment_service",
    "mir_training_service",
    "mir_feature_service",
    "cir_combat_factor_experiment_service",
    "cir_feature_pruning_service",
    "cir_final_validation_service",
    "experiment_mir",
    "experiment_cir_features",
    "experiment_cir_final",
    "experiment_cir_combat_factor",
    "experiment_context_v2",
)


def test_production_api_does_not_import_research_metric_paths() -> None:
    files: list[Path] = []
    for path in PRODUCTION_PATHS:
        if path.is_file():
            files.append(path)
        else:
            files.extend(path.glob("*.py"))
    combined = "\n".join(path.read_text() for path in files)
    for token in FORBIDDEN_IMPORT_TOKENS:
        assert token not in combined, f"production API imports research path {token}"
