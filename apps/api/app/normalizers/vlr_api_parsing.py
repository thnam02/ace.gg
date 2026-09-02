from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from app.parsers.numbers import parse_int, parse_optional_int

_DATE_RANGE = re.compile(
    r"(?P<start>[A-Za-z]{3,9}\s+\d{1,2})\s*[–\-—]\s*(?P<end>[A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})",
    re.IGNORECASE,
)
_SAME_MONTH_RANGE = re.compile(
    r"(?P<month>[A-Za-z]{3,9})\s+(?P<start_day>\d{1,2})\s*[–\-—]\s*"
    r"(?P<end_day>\d{1,2}),\s*(?P<year>20\d{2})",
    re.IGNORECASE,
)
_SINGLE_DATE = re.compile(r"([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})")
_YEAR = re.compile(r"\b(20\d{2})\b")
_VLR_WEEKDAY_DATETIME = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
    r"(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2})\s+"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})\s+(?P<ampm>AM|PM)"
    r"(?:\s+(?P<tz>[A-Z]{2,5}))?",
    re.IGNORECASE,
)
_TZ_OFFSETS: dict[str, timezone] = {
    "UTC": UTC,
    "GMT": UTC,
    "AEST": timezone(timedelta(hours=10)),
    "AEDT": timezone(timedelta(hours=11)),
    "ACST": timezone(timedelta(hours=9, minutes=30)),
    "ACDT": timezone(timedelta(hours=10, minutes=30)),
    "PST": timezone(timedelta(hours=-8)),
    "PDT": timezone(timedelta(hours=-7)),
    "MST": timezone(timedelta(hours=-7)),
    "MDT": timezone(timedelta(hours=-6)),
    "CST": timezone(timedelta(hours=-6)),
    "CDT": timezone(timedelta(hours=-5)),
    "EST": timezone(timedelta(hours=-5)),
    "EDT": timezone(timedelta(hours=-4)),
    "BST": timezone(timedelta(hours=1)),
    "CET": timezone(timedelta(hours=1)),
    "CEST": timezone(timedelta(hours=2)),
    "EET": timezone(timedelta(hours=2)),
    "EEST": timezone(timedelta(hours=3)),
    "IST": timezone(timedelta(hours=5, minutes=30)),
    "JST": timezone(timedelta(hours=9)),
    "KST": timezone(timedelta(hours=9)),
    "SGT": timezone(timedelta(hours=8)),
    "HKT": timezone(timedelta(hours=8)),
    "CST+8": timezone(timedelta(hours=8)),
}

_COUNTRY_REGION: dict[str, str] = {
    "united states": "NA",
    "canada": "NA",
    "brazil": "BR",
    "chile": "SA",
    "argentina": "SA",
    "mexico": "NA",
    "korea": "KR",
    "south korea": "KR",
    "japan": "AP",
    "china": "CN",
    "australia": "OCE",
    "united kingdom": "EU",
    "germany": "EU",
    "france": "EU",
    "spain": "EU",
    "italy": "EU",
    "poland": "EU",
    "turkey": "EU",
}


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def normalize_player_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def unwrap_match_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept fixture-style match objects or live vlrggapi `{segments: [match]}`."""
    if payload.get("match_id") is not None and payload.get("maps") is not None:
        return payload
    segments = payload.get("segments")
    if isinstance(segments, list) and segments:
        first = as_dict(segments[0])
        if first.get("match_id") is not None or first.get("maps") is not None:
            return first
    return payload


def unwrap_team_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept fixture-style team objects or live vlrggapi `{segments: [team]}`."""
    current = payload
    nested = as_dict(current.get("data"))
    if nested:
        current = nested
    if current.get("roster") is not None or current.get("players") is not None:
        return current
    segments = current.get("segments")
    if isinstance(segments, list) and segments:
        first = as_dict(segments[0])
        if first:
            return first
    if isinstance(segments, dict):
        return segments
    return current


def parse_team_roster_players(payload: dict[str, Any]) -> list[tuple[int, str]]:
    team = unwrap_team_payload(payload)
    roster = as_list(team.get("roster")) or as_list(team.get("players"))
    players: list[tuple[int, str]] = []
    for entry in roster:
        row = as_dict(entry)
        if _is_truthy(row.get("is_staff")):
            continue
        player_id = parse_vlr_id(row.get("id"))
        handle = str(row.get("alias") or row.get("name") or "").strip()
        if player_id is None or not handle:
            continue
        players.append((player_id, handle))
    return players


def unwrap_player_profile(payload: dict[str, Any]) -> dict[str, Any]:
    current = payload
    nested = as_dict(current.get("data"))
    if nested:
        current = nested
    if (
        current.get("info") is not None
        or current.get("current_team") is not None
        or current.get("current_teams") is not None
        or current.get("past_teams") is not None
        or current.get("name")
    ):
        if current.get("segments") is None:
            return current
    segments = current.get("segments")
    if isinstance(segments, list) and segments:
        first = as_dict(segments[0])
        if first:
            return first
    if isinstance(segments, dict):
        return segments
    return current


def parse_player_profile_handle(payload: dict[str, Any]) -> str:
    profile = unwrap_player_profile(payload)
    info = as_dict(profile.get("info"))
    return str(info.get("name") or profile.get("name") or "").strip()


def parse_player_profile_teams(payload: dict[str, Any]) -> list[dict[str, Any]]:
    profile = unwrap_player_profile(payload)
    teams: list[dict[str, Any]] = []
    current = profile.get("current_team")
    if isinstance(current, dict) and (current.get("name") or current.get("tag")):
        teams.append(current)
    for item in as_list(profile.get("current_teams")):
        row = as_dict(item)
        if row.get("name") or row.get("tag"):
            teams.append(row)
    for item in as_list(profile.get("past_teams")):
        row = as_dict(item)
        if row.get("name") or row.get("tag"):
            teams.append(row)
    return teams


def parse_search_players(payload: dict[str, Any]) -> list[dict[str, Any]]:
    current = payload
    nested = as_dict(current.get("data"))
    if nested:
        current = nested
    segments = current.get("segments")
    results: dict[str, Any] = {}
    if isinstance(segments, dict):
        results = as_dict(segments.get("results"))
    elif isinstance(segments, list) and segments:
        results = as_dict(as_dict(segments[0]).get("results"))
    else:
        results = as_dict(current.get("results"))
    return [as_dict(item) for item in as_list(results.get("players"))]


def search_result_handle(row: dict[str, Any]) -> str:
    raw = str(row.get("name") or row.get("alias") or "").strip()
    return raw.split("(")[0].strip()


def normalize_team_token(value: str) -> str:
    return " ".join(value.strip().lower().split())


def profile_matches_team(
    payload: dict[str, Any],
    *,
    team_name: str | None,
    team_tag: str | None,
) -> bool:
    tokens = {
        token
        for token in (
            normalize_team_token(team_name or ""),
            normalize_team_token(team_tag or ""),
        )
        if token
    }
    if not tokens:
        return False
    for team in parse_player_profile_teams(payload):
        name = normalize_team_token(str(team.get("name") or ""))
        tag = normalize_team_token(str(team.get("tag") or ""))
        if name and name in tokens:
            return True
        if tag and tag in tokens:
            return True
    return False


def profile_has_team_evidence(payload: dict[str, Any]) -> bool:
    return bool(parse_player_profile_teams(payload))


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "staff"}


def event_match_entries(payload: dict[str, Any]) -> list[Any]:
    matches = as_list(payload.get("matches"))
    if matches:
        return matches
    segments = payload.get("segments")
    if isinstance(segments, list):
        return segments
    return []


def parse_map_team_score(value: Any) -> int | None:
    if isinstance(value, dict):
        return parse_optional_int(value.get("total", value.get("score")))
    return parse_optional_int(value)


def parse_vlr_id(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    return None


def team_tag_from_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        return "UNK"
    if len(cleaned) <= 4:
        return cleaned.upper()
    words = [word for word in re.split(r"\s+", cleaned) if word]
    if len(words) >= 2 and all(len(word) <= 4 for word in words):
        return "".join(word[0] for word in words).upper()
    return cleaned[:3].upper()


def country_to_region(country: str | None) -> str | None:
    if not country:
        return None
    return _COUNTRY_REGION.get(country.strip().lower())


def parse_date_text(text: str | None) -> date | None:
    if not text:
        return None
    cleaned = " ".join(text.split())
    single = _SINGLE_DATE.search(cleaned)
    if single:
        try:
            return datetime.strptime(single.group(1), "%b %d, %Y").date()
        except ValueError:
            return None
    return None


def parse_date_range_text(text: str | None) -> tuple[date | None, date | None]:
    if not text:
        return None, None
    cleaned = " ".join(text.split())
    same_month = _SAME_MONTH_RANGE.search(cleaned)
    if same_month:
        month = same_month.group("month")
        year = same_month.group("year")
        try:
            start_date = datetime.strptime(
                f"{month} {same_month.group('start_day')}, {year}",
                "%b %d, %Y",
            ).date()
            end_date = datetime.strptime(
                f"{month} {same_month.group('end_day')}, {year}",
                "%b %d, %Y",
            ).date()
            return start_date, end_date
        except ValueError:
            pass
    match = _DATE_RANGE.search(cleaned)
    if match:
        end_text = match.group("end")
        start_text = match.group("start")
        year_match = _YEAR.search(end_text)
        if not year_match:
            return None, None
        year = year_match.group(1)
        try:
            end_date = datetime.strptime(end_text, "%b %d, %Y").date()
            start_date = datetime.strptime(f"{start_text}, {year}", "%b %d, %Y").date()
            return start_date, end_date
        except ValueError:
            return None, None
    single = parse_date_text(cleaned)
    if single is not None:
        return single, single
    return None, None


def year_from_text(text: str | None) -> int | None:
    if not text:
        return None
    match = _YEAR.search(text)
    if match is None:
        return None
    return int(match.group(1))


def parse_datetime_text(
    text: str | None,
    *,
    default_year: int | None = None,
) -> datetime | None:
    if not text:
        return None
    cleaned = " ".join(text.split())
    weekday_match = _VLR_WEEKDAY_DATETIME.search(cleaned)
    if weekday_match:
        year_match = _YEAR.search(cleaned)
        year = int(year_match.group(1)) if year_match else default_year
        if year is None:
            return None
        month_text = weekday_match.group("month")
        try:
            month = datetime.strptime(month_text[:3], "%b").month
        except ValueError:
            return None
        hour = int(weekday_match.group("hour"))
        ampm = weekday_match.group("ampm").upper()
        if ampm == "PM" and hour != 12:
            hour += 12
        if ampm == "AM" and hour == 12:
            hour = 0
        tz_key = (weekday_match.group("tz") or "UTC").upper()
        tzinfo = _TZ_OFFSETS.get(tz_key, UTC)
        local = datetime(
            year,
            month,
            int(weekday_match.group("day")),
            hour,
            int(weekday_match.group("minute")),
            tzinfo=tzinfo,
        )
        return local.astimezone(UTC)
    parsed = parse_date_text(cleaned)
    if parsed is None:
        return None
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)


def parse_best_of(map_vetos: str | None, map_count: int) -> int | None:
    if map_vetos:
        lowered = map_vetos.lower()
        bo_match = re.search(r"\bbo\s*(\d+)\b", lowered)
        if bo_match:
            return int(bo_match.group(1))
    if map_count >= 3:
        return 3
    if map_count == 1:
        return 1
    if map_count == 2:
        return 3
    return None


def clutch_stats_from_advanced(
    performance: dict[str, Any],
    player_name: str,
) -> tuple[int | None, int | None]:
    advanced = as_list(performance.get("advanced_stats"))
    normalized_name = player_name.strip().lower()
    for entry in advanced:
        row = as_dict(entry)
        if str(row.get("player") or "").strip().lower() != normalized_name:
            continue
        clutch_attempts = 0
        clutch_wins = 0
        found_clutch_field = False
        for key, value in row.items():
            key_lower = str(key).lower()
            if "clutch" not in key_lower:
                continue
            found_clutch_field = True
            count = parse_int(value, default=0)
            clutch_attempts += count
            if "win" in key_lower or key_lower.endswith("1v1"):
                clutch_wins += count
        if not found_clutch_field:
            return None, None
        return clutch_wins, clutch_attempts
    return None, None


def max_kills_from_advanced(
    performance: dict[str, Any],
    player_name: str,
) -> int | None:
    advanced = as_list(performance.get("advanced_stats"))
    normalized_name = player_name.strip().lower()
    for entry in advanced:
        row = as_dict(entry)
        if str(row.get("player") or "").strip().lower() != normalized_name:
            continue
        values = [
            parse_optional_int(row.get("5K")),
            parse_optional_int(row.get("5k")),
            parse_optional_int(row.get("4K")),
            parse_optional_int(row.get("4k")),
        ]
        present = [value for value in values if value is not None]
        return max(present) if present else None
    return None
