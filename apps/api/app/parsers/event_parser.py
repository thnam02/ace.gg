from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from app.parsers.match_parser import _as_tag, _attr, _class_list, _id_from_href, _text
from app.schemas.ingestion import NormalizedEvent, NormalizedEventPageData, NormalizedTeam

_EVENT_HREF = re.compile(r"/event/(\d+)", re.IGNORECASE)
_TEAM_HREF = re.compile(r"/team/(\d+)", re.IGNORECASE)
_MATCH_PATH = re.compile(r"^/(?P<id>\d+)/[^/]+/?$", re.IGNORECASE)
_DATE_RANGE = re.compile(
    r"(?P<start>[A-Za-z]{3,9}\s+\d{1,2})\s*[–\-—]\s*(?P<end>[A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})",
    re.IGNORECASE,
)
_SINGLE_DATE = re.compile(r"([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})")
_YEAR = re.compile(r"\b(20\d{2})\b")
_REGION_FLAGS: dict[str, str] = {
    "na": "NA",
    "us": "NA",
    "br": "BR",
    "eu": "EU",
    "kr": "KR",
    "ap": "AP",
    "jp": "AP",
    "cn": "CN",
    "oce": "OCE",
    "sa": "SA",
}


class EventParser:
    """Parse VLR event HTML into metadata, teams, and match IDs."""

    def parse(self, html: str, *, event_id: int | None = None) -> NormalizedEventPageData:
        if not html or not html.strip():
            raise ValueError("Event HTML is empty")

        soup = BeautifulSoup(html, "html.parser")
        resolved_event_id = event_id or _extract_event_id(soup)
        if resolved_event_id is None:
            raise ValueError("Could not determine VLR event ID")

        name = _parse_event_name(soup, resolved_event_id)
        region = _parse_region(soup)
        start_date, end_date = _parse_dates(soup, name)
        status = _parse_status(soup)
        tier = _parse_tier(soup)
        teams = _parse_participating_teams(soup)
        match_ids = self.discover_match_ids(html, event_id=resolved_event_id)

        event = NormalizedEvent(
            vlr_event_id=resolved_event_id,
            name=name,
            region=region,
            tier=tier,
            start_date=start_date,
            end_date=end_date,
            season_year=_season_year(name, end_date, start_date),
            status=status,
        )
        return NormalizedEventPageData(
            event=event,
            participating_teams=teams,
            match_ids=match_ids,
        )

    def discover_match_ids(self, html: str, *, event_id: int | None = None) -> list[int]:
        if not html or not html.strip():
            return []

        soup = BeautifulSoup(html, "html.parser")
        resolved_event_id = event_id or _extract_event_id(soup)
        discovered: list[int] = []
        seen: set[int] = set()

        for link in soup.select("a[href]"):
            tag = _as_tag(link)
            if tag is None:
                continue
            href = _attr(tag, "href")
            if not href:
                continue
            match_id = _match_id_from_href(href, resolved_event_id)
            if match_id is None or match_id in seen:
                continue
            seen.add(match_id)
            discovered.append(match_id)

        return discovered


def _extract_event_id(soup: BeautifulSoup) -> int | None:
    canonical = _as_tag(soup.find("link", rel="canonical"))
    if canonical is not None:
        event_id = _id_from_href(_attr(canonical, "href"), _EVENT_HREF)
        if event_id is not None:
            return event_id

    og_url = _as_tag(soup.find("meta", property="og:url"))
    if og_url is not None:
        event_id = _id_from_href(_attr(og_url, "content"), _EVENT_HREF)
        if event_id is not None:
            return event_id

    for link in soup.select("a[href*='/event/']"):
        tag = _as_tag(link)
        event_id = _id_from_href(_attr(tag, "href"), _EVENT_HREF)
        if event_id is not None:
            return event_id
    return None


def _parse_event_name(soup: BeautifulSoup, event_id: int) -> str:
    selectors = (
        ".event-header-title",
        ".event-item-title",
        "h1.wf-title-med",
        "h1",
        ".event-header .wf-title-med",
    )
    for selector in selectors:
        node = _as_tag(soup.select_one(selector))
        if node is not None:
            name = _text(node)
            if name:
                return name

    title = _as_tag(soup.find("title"))
    if title is not None:
        raw = _text(title)
        if raw:
            return raw.split("|")[0].strip()

    return f"Event {event_id}"


def _parse_status(soup: BeautifulSoup) -> str | None:
    selectors = (
        ".event-desc-item-status",
        ".event-item-desc-item-status",
        ".event-header-status",
        ".event-status",
    )
    for selector in selectors:
        node = _as_tag(soup.select_one(selector))
        if node is not None:
            status = _text(node)
            if status:
                return status.lower()
    return None


def _parse_tier(soup: BeautifulSoup) -> str | None:
    selectors = (
        ".event-desc-item.mod-tier",
        ".event-item-desc-item.mod-tier",
        ".event-header-tier",
    )
    for selector in selectors:
        node = _as_tag(soup.select_one(selector))
        if node is not None:
            tier = _text(node)
            if tier:
                return tier
    return None


def _parse_region(soup: BeautifulSoup) -> str | None:
    location = _as_tag(
        soup.select_one(".event-desc-item.mod-location")
        or soup.select_one(".event-item-desc-item.mod-location")
    )
    if location is None:
        return None

    flag = _as_tag(location.select_one(".flag"))
    if flag is not None:
        for class_name in _class_list(flag):
            if class_name.startswith("mod-") and class_name != "mod-":
                code = class_name.removeprefix("mod-").lower()
                if code in _REGION_FLAGS:
                    return _REGION_FLAGS[code]

    text = _text(location)
    if text:
        lowered = text.lower()
        for keyword, region in (
            ("north america", "NA"),
            ("south america", "SA"),
            ("brazil", "BR"),
            ("europe", "EU"),
            ("korea", "KR"),
            ("asia", "AP"),
            ("oceania", "OCE"),
            ("china", "CN"),
        ):
            if keyword in lowered:
                return region
        return text
    return None


def _parse_dates(soup: BeautifulSoup, event_name: str) -> tuple[date | None, date | None]:
    selectors = (
        ".event-desc-item.mod-dates",
        ".event-item-desc-item.mod-dates",
        ".event-header-date",
    )
    for selector in selectors:
        node = _as_tag(soup.select_one(selector))
        if node is not None:
            parsed = _parse_date_range_text(_text(node))
            if parsed != (None, None):
                return parsed

    return _parse_date_range_text(event_name)


def _parse_date_range_text(text: str) -> tuple[date | None, date | None]:
    if not text:
        return None, None

    match = _DATE_RANGE.search(text)
    if match is not None:
        year_match = _YEAR.search(match.group("end"))
        year = int(year_match.group(1)) if year_match else None
        start = _parse_partial_date(match.group("start"), year)
        end = _parse_partial_date(match.group("end"), year)
        return start, end

    single = _SINGLE_DATE.search(text)
    if single is not None:
        parsed = _parse_partial_date(single.group(1), None)
        return parsed, parsed

    return None, None


def _parse_partial_date(value: str, year: int | None) -> date | None:
    cleaned = value.strip().replace(",", "")
    parts = cleaned.split()
    if len(parts) < 2:
        return None

    month_token = parts[0][:3].title()
    day_token = parts[1]
    year_token = parts[2] if len(parts) > 2 else None
    resolved_year = int(year_token) if year_token and year_token.isdigit() else year
    if resolved_year is None:
        return None

    try:
        from datetime import datetime

        parsed = datetime.strptime(f"{month_token} {day_token} {resolved_year}", "%b %d %Y")
        return parsed.date()
    except ValueError:
        return None


def _season_year(
    name: str,
    end_date: date | None,
    start_date: date | None,
) -> int | None:
    if end_date is not None:
        return end_date.year
    if start_date is not None:
        return start_date.year
    match = _YEAR.search(name)
    return int(match.group(1)) if match else None


def _parse_participating_teams(soup: BeautifulSoup) -> list[NormalizedTeam]:
    teams: list[NormalizedTeam] = []
    seen: set[int] = set()

    containers = soup.select(
        ".event-teams-container a[href*='/team/'], "
        ".event-participants a[href*='/team/'], "
        "a.event-team[href*='/team/'], "
        ".wf-card.event-team[href*='/team/']"
    )
    for link in containers:
        tag = _as_tag(link)
        if tag is None:
            continue
        vlr_team_id = _id_from_href(_attr(tag, "href"), _TEAM_HREF)
        if vlr_team_id is None or vlr_team_id in seen:
            continue

        name_node = _as_tag(
            tag.select_one(".wf-title-med")
            or tag.select_one(".event-team-name")
            or tag.select_one(".text-of")
        )
        name = _text(name_node) or _text(tag)
        if not name:
            continue

        tag_node = _as_tag(tag.select_one(".ge-text-light"))
        team_tag = _text(tag_node) or name[:3].upper()

        teams.append(
            NormalizedTeam(
                vlr_team_id=vlr_team_id,
                name=name,
                tag=team_tag,
            )
        )
        seen.add(vlr_team_id)

    return teams


def _match_id_from_href(href: str, event_id: int | None) -> int | None:
    if "/team/" in href or "/player/" in href or "/event/" in href:
        return None

    path = href.split("vlr.gg", 1)[-1]
    if path.startswith("http"):
        return None
    if not path.startswith("/"):
        path = f"/{path}"

    match = _MATCH_PATH.match(path.split("?", 1)[0])
    if match is None:
        return None

    match_id = int(match.group("id"))
    if event_id is not None and match_id == event_id:
        return None
    return match_id
