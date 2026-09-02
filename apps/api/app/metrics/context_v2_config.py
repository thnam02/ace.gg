from __future__ import annotations

from dataclasses import dataclass, field

from app.metrics.context_v2 import ContextV2Level, FeatureContextRule

CONTEXT_MODE_V1 = "context_v1"
CONTEXT_MODE_V2 = "context_v2"
CONTEXT_MODE_NONE = "no_context"

LAMBDA_CANDIDATES: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)
TAU_CANDIDATES: tuple[float, ...] = (50.0, 100.0, 200.0, 500.0)
CONTEXT_SHRINKAGE_K_CANDIDATES: tuple[float, ...] = (50.0, 100.0, 250.0, 500.0)

# Relative RMSE slack used as a "similar performance" band before preferring simplicity.
SELECTION_RMSE_RELATIVE_SLACK = 0.01
SELECTION_ROLE_GAP_SOFT_LIMIT = 8.0


def feature_specific_rules() -> dict[str, FeatureContextRule]:
    """Default v2 hypotheses: lighter combat context, agent-aware APR, no extra ADR."""
    return {
        "kpr": FeatureContextRule("kpr", ContextV2Level.ROLE_TIER),
        "dpr": FeatureContextRule("dpr", ContextV2Level.ROLE_TIER),
        "apr": FeatureContextRule("apr", ContextV2Level.AGENT_TIER),
        "kast": FeatureContextRule("kast", ContextV2Level.ROLE_TIER),
        "opening_frequency": FeatureContextRule("opening_frequency", ContextV2Level.ROLE),
        "opening_efficiency": FeatureContextRule("opening_efficiency", ContextV2Level.ROLE),
        "residual_adr": FeatureContextRule("residual_adr", ContextV2Level.NONE),
        "clutch": FeatureContextRule("clutch", ContextV2Level.NONE),
    }


def rules_to_dict(rules: dict[str, FeatureContextRule]) -> dict[str, str]:
    return {name: rule.level.value for name, rule in rules.items()}


@dataclass(frozen=True)
class ContextExperimentSpec:
    name: str
    mode: str
    lam: float = 1.0
    tau: float = 0.0
    hierarchical: bool = False
    tune_lambda: bool = False
    tune_tau: bool = False
    rules: dict[str, FeatureContextRule] = field(default_factory=feature_specific_rules)
    simplicity_rank: int = 0

    def configuration(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "lambda": self.lam,
            "tau": self.tau,
            "hierarchical": self.hierarchical,
            "tune_lambda": self.tune_lambda,
            "tune_tau": self.tune_tau,
            "feature_rules": rules_to_dict(self.rules),
        }


def default_context_experiment_matrix() -> dict[str, ContextExperimentSpec]:
    rules = feature_specific_rules()
    return {
        "no_context": ContextExperimentSpec(
            name="no_context",
            mode=CONTEXT_MODE_NONE,
            lam=0.0,
            tau=0.0,
            simplicity_rank=0,
        ),
        "context_v1": ContextExperimentSpec(
            name="context_v1",
            mode=CONTEXT_MODE_V1,
            lam=1.0,
            tau=0.0,
            simplicity_rank=6,
        ),
        "context_v2_feature_specific_full": ContextExperimentSpec(
            name="context_v2_feature_specific_full",
            mode=CONTEXT_MODE_V2,
            lam=1.0,
            tau=0.0,
            rules=rules,
            simplicity_rank=4,
        ),
        "context_v2_partial_lambda_0.25": ContextExperimentSpec(
            name="context_v2_partial_lambda_0.25",
            mode=CONTEXT_MODE_V2,
            lam=0.25,
            tau=0.0,
            rules=rules,
            simplicity_rank=1,
        ),
        "context_v2_partial_lambda_0.5": ContextExperimentSpec(
            name="context_v2_partial_lambda_0.5",
            mode=CONTEXT_MODE_V2,
            lam=0.5,
            tau=0.0,
            rules=rules,
            simplicity_rank=2,
        ),
        "context_v2_partial_lambda_0.75": ContextExperimentSpec(
            name="context_v2_partial_lambda_0.75",
            mode=CONTEXT_MODE_V2,
            lam=0.75,
            tau=0.0,
            rules=rules,
            simplicity_rank=3,
        ),
        "hierarchical_shrunk_context": ContextExperimentSpec(
            name="hierarchical_shrunk_context",
            mode=CONTEXT_MODE_V2,
            lam=1.0,
            tau=200.0,
            hierarchical=True,
            tune_tau=True,
            rules=rules,
            simplicity_rank=5,
        ),
    }


def recommended_context_v2_spec() -> ContextExperimentSpec:
    """Context v2 settings selected after the context experiment (not production default)."""
    return ContextExperimentSpec(
        name="context_v2_recommended",
        mode=CONTEXT_MODE_V2,
        lam=1.0,
        tau=500.0,
        hierarchical=True,
        rules=feature_specific_rules(),
        simplicity_rank=5,
    )


def register_context_experiment(
    matrix: dict[str, ContextExperimentSpec],
    spec: ContextExperimentSpec,
) -> dict[str, ContextExperimentSpec]:
    """Extend an experiment matrix without changing training code."""
    updated = dict(matrix)
    updated[spec.name] = spec
    return updated
