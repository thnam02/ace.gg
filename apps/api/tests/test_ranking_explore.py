from uuid import uuid4

from app.metrics.cir.ranking_explore import (
    canonicalize_ranking_region,
    event_ranking_region,
    pick_ranking_region,
    snapshot_event_ids,
)


def test_canonicalize_and_infer_regions() -> None:
    assert canonicalize_ranking_region("NA") == "Americas"
    assert canonicalize_ranking_region("AP") == "Pacific"
    assert canonicalize_ranking_region("EMEA") == "EMEA"
    assert (
        event_ranking_region(
            region=None,
            name="Challengers 2026: EMEA Stage 3",
        )
        == "EMEA"
    )
    assert (
        event_ranking_region(
            region=None,
            name="Challengers 2026: North America ACE Stage 2",
        )
        == "Americas"
    )
    assert (
        event_ranking_region(
            region=None,
            name="Challengers 2026: Southeast Asia Split 2",
        )
        == "Pacific"
    )
    assert (
        event_ranking_region(
            region="INTL",
            name="Valorant Champions 2026",
        )
        == "INTL"
    )


def test_pick_region_prefers_league_over_intl_and_falls_back_to_team() -> None:
    assert (
        pick_ranking_region(
            team_region="NA",
            event_regions=["Americas", "INTL", "INTL"],
        )
        == "Americas"
    )
    assert pick_ranking_region(team_region="NA", event_regions=["INTL"]) == "INTL"
    assert pick_ranking_region(team_region="NA", event_regions=[]) == "Americas"
    assert pick_ranking_region(team_region=None, event_regions=[]) is None


def test_snapshot_event_ids_skip_invalid_values() -> None:
    event_id = uuid4()
    assert snapshot_event_ids({"event_ids": [str(event_id), "not-a-uuid", 12]}) == [event_id]
    assert snapshot_event_ids({}) == []
