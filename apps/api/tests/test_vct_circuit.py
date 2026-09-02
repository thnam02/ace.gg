from __future__ import annotations

from pathlib import Path

from app.normalizers.event_status import canonical_event_status, is_completed_match_status
from app.normalizers.vct_circuit import (
    parse_vct_circuit_page,
    parse_vct_date_range,
    vct_region_from_name,
    vct_stage_from_name,
)
from app.providers.vct_circuit_provider import StaticVctCircuitProvider
from app.schemas.vct_circuit import EventStatus, VctRegion, VctStage
from app.services.vct_circuit_discovery import VctCircuitDiscoveryService

FIXTURE = Path(__file__).parent / "fixtures" / "vct_circuit.html"


def test_parse_vct_circuit_statuses_regions_and_stages() -> None:
    events = parse_vct_circuit_page(FIXTURE.read_text(encoding="utf-8"), season_year=2026)
    by_id = {item.vlr_event_id: item for item in events}
    assert set(by_id) == {2977, 2766, 2860, 2760}

    ongoing = by_id[2977]
    assert ongoing.status == EventStatus.ONGOING
    assert ongoing.region == VctRegion.AMERICAS.value
    assert ongoing.stage == VctStage.STAGE_2.value
    assert ongoing.tier == "T1"
    assert ongoing.circuit == "VCT"
    assert ongoing.season_year == 2026
    assert ongoing.start_date is not None and ongoing.start_date.month == 7

    upcoming = by_id[2766]
    assert upcoming.status == EventStatus.UPCOMING
    assert upcoming.region == VctRegion.INTL.value
    assert upcoming.stage == VctStage.CHAMPIONS.value

    completed = by_id[2860]
    assert completed.status == EventStatus.COMPLETED
    assert completed.region == VctRegion.AMERICAS.value
    assert completed.stage == VctStage.STAGE_1.value

    masters = by_id[2760]
    assert masters.region == VctRegion.INTL.value
    assert masters.stage == VctStage.MASTERS.value


def test_discovery_service_uses_injected_page() -> None:
    service = VctCircuitDiscoveryService(
        StaticVctCircuitProvider(FIXTURE.read_text(encoding="utf-8")),
        season_year=2026,
    )
    events = service.discover()
    assert [item.vlr_event_id for item in events] == [2977, 2766, 2860, 2760]


def test_vct_date_range_without_year() -> None:
    start, end = parse_vct_date_range("Jun 5—21", year=2026)
    assert start is not None and start.month == 6 and start.day == 5
    assert end is not None and end.month == 6 and end.day == 21


def test_region_and_stage_normalization() -> None:
    assert vct_region_from_name("VCT 2026: Pacific Kickoff") == VctRegion.PACIFIC.value
    assert vct_region_from_name("VCT 2026: China Stage 1") == VctRegion.CHINA.value
    assert vct_region_from_name("VCT 2026: EMEA Stage 2") == VctRegion.EMEA.value
    assert vct_stage_from_name("VCT 2026: Americas Kickoff") == VctStage.KICKOFF.value


def test_canonical_event_and_match_status() -> None:
    assert canonical_event_status("completed") == EventStatus.COMPLETED
    assert canonical_event_status("live") == EventStatus.ONGOING
    assert canonical_event_status("UPCOMING") == EventStatus.UPCOMING
    assert is_completed_match_status("Completed") is True
    assert is_completed_match_status("Upcoming") is False
    assert is_completed_match_status("2d 4h") is False
