from __future__ import annotations

import pytest

from app.providers.vlr_provider import (
    FileVLRProvider,
    StaticVLRProvider,
    UnsupportedVLRResourceError,
)
from tests.vlr_fixtures import FIXTURES_DIR, load_match_html


def test_file_provider_loads_match_html_by_id() -> None:
    provider = FileVLRProvider(FIXTURES_DIR)
    html = provider.get_match(900001)
    assert "Sentinels" in html
    assert "900001" in html


def test_static_provider_is_not_hard_coded_to_a_match() -> None:
    provider = StaticVLRProvider({42: load_match_html("900002_bo1_completed.html")})
    html = provider.get_match(42)
    assert "Gen.G" in html
    with pytest.raises(FileNotFoundError):
        provider.get_match(900002)


def test_unimplemented_vlr_resources_are_explicit() -> None:
    provider = FileVLRProvider(FIXTURES_DIR)
    with pytest.raises(UnsupportedVLRResourceError):
        provider.get_event(1)
    with pytest.raises(UnsupportedVLRResourceError):
        provider.get_event_matches(1)
    with pytest.raises(UnsupportedVLRResourceError):
        provider.get_player(1)
    with pytest.raises(UnsupportedVLRResourceError):
        provider.get_team(1)
