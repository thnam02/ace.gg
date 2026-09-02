from __future__ import annotations

import re
from datetime import UTC, date, datetime
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


def parse_datetime_text(text: str | None) -> datetime | None:
    parsed = parse_date_text(text)
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
