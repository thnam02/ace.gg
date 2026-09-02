from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScaleEventSpec:
    vlr_event_id: int
    tier: str
    region: str
    label: str


# Completed 2026 events only. Americas/Pacific Stage 2 and Champions 2026 were still
# ongoing/upcoming as of 2026-09-02 and are intentionally excluded.
SCALE_EVENT_SET: tuple[ScaleEventSpec, ...] = (
    ScaleEventSpec(2857, "T2", "NA", "Challengers 2026: North America ACE Stage 2"),
    ScaleEventSpec(2775, "T1", "Pacific", "VCT 2026: Pacific Stage 1"),
    ScaleEventSpec(2860, "T1", "Americas", "VCT 2026: Americas Stage 1"),
    ScaleEventSpec(2765, "T1", "INTL", "Valorant Masters London 2026"),
    ScaleEventSpec(3016, "T2", "EMEA", "Challengers 2026: EMEA Stage 3"),
    ScaleEventSpec(2825, "T2", "Pacific", "Challengers 2026: Southeast Asia Split 2"),
    ScaleEventSpec(2978, "T1", "China", "VCT 2026: China Stage 2"),
    ScaleEventSpec(2976, "T1", "EMEA", "VCT 2026: EMEA Stage 2"),
)

SCALE_EVENT_IDS: tuple[int, ...] = tuple(item.vlr_event_id for item in SCALE_EVENT_SET)

CIR_REAL_EXPERIMENT_VERSION = "v0.1-real-2026"
