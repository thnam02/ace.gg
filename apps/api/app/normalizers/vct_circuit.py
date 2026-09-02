from __future__ import annotations

import re
from datetime import date, datetime

from bs4 import BeautifulSoup, Tag

from app.normalizers.event_status import canonical_event_status
from app.schemas.vct_circuit import (
    CircuitName,
    EventStatus,
    VctDiscoveredEvent,
    VctRegion,
    VctStage,
)

_EVENT_HREF = re.compile(r"/event/(\d+)(?:/([^/?#]+))?")
_YEAR = re.compile(r"\b(20\d{2})\b")
_CROSS_MONTH = re.compile(
    r"(?P<start_month>[A-Za-z]{3,9})\s+(?P<start_day>\d{1,2})\s*[–\-—]\s*"
    r"(?P<end_month>[A-Za-z]{3,9})\s+(?P<end_day>\d{1,2})",
    re.IGNORECASE,
)
_SAME_MONTH = re.compile(
    r"(?P<month>[A-Za-z]{3,9})\s+(?P<start_day>\d{1,2})\s*[–\-—]\s*(?P<end_day>\d{1,2})",
    re.IGNORECASE,
)

_FLAG_REGION: dict[str, str] = {
    "us": VctRegion.AMERICAS.value,
    "ca": VctRegion.AMERICAS.value,
    "br": VctRegion.AMERICAS.value,
    "mx": VctRegion.AMERICAS.value,
    "de": VctRegion.EMEA.value,
    "fr": VctRegion.EMEA.value,
    "gb": VctRegion.EMEA.value,
    "uk": VctRegion.EMEA.value,
    "es": VctRegion.EMEA.value,
    "tr": VctRegion.EMEA.value,
    "pl": VctRegion.EMEA.value,
    "kr": VctRegion.PACIFIC.value,
    "jp": VctRegion.PACIFIC.value,
    "vn": VctRegion.PACIFIC.value,
    "th": VctRegion.PACIFIC.value,
    "id": VctRegion.PACIFIC.value,
    "sg": VctRegion.PACIFIC.value,
    "au": VctRegion.PACIFIC.value,
    "cn": VctRegion.CHINA.value,
    "cl": VctRegion.INTL.value,
    "un": VctRegion.INTL.value,
}


def parse_vct_circuit_page(
    html: str,
    *,
    season_year: int = 2026,
) -> list[VctDiscoveredEvent]:
    soup = BeautifulSoup(html, "html.parser")
    year = _season_year_from_page(soup, season_year)
    events: list[VctDiscoveredEvent] = []
    seen: set[int] = set()
    for item in soup.select("a.event-item"):
        parsed = _parse_event_card(item, season_year=year)
        if parsed is None or parsed.vlr_event_id in seen:
            continue
        seen.add(parsed.vlr_event_id)
        events.append(parsed)
    return events


def vct_region_from_name(name: str, *, flag_code: str | None = None) -> str:
    lowered = name.lower()
    if "americas" in lowered:
        return VctRegion.AMERICAS.value
    if "emea" in lowered:
        return VctRegion.EMEA.value
    if "pacific" in lowered:
        return VctRegion.PACIFIC.value
    if "china" in lowered:
        return VctRegion.CHINA.value
    if "masters" in lowered or "champions" in lowered:
        return VctRegion.INTL.value
    if flag_code:
        return _FLAG_REGION.get(flag_code.lower(), VctRegion.INTL.value)
    return VctRegion.INTL.value


def vct_stage_from_name(name: str) -> str | None:
    lowered = name.lower()
    if "kickoff" in lowered:
        return VctStage.KICKOFF.value
    if "masters" in lowered:
        return VctStage.MASTERS.value
    if "champions" in lowered:
        return VctStage.CHAMPIONS.value
    if "stage 2" in lowered or "stage2" in lowered:
        return VctStage.STAGE_2.value
    if "stage 1" in lowered or "stage1" in lowered:
        return VctStage.STAGE_1.value
    return None


def parse_vct_date_range(text: str | None, *, year: int) -> tuple[date | None, date | None]:
    if not text:
        return None, None
    cleaned = " ".join(text.split())
    cross = _CROSS_MONTH.search(cleaned)
    if cross:
        start = _parse_month_day(cross.group("start_month"), cross.group("start_day"), year)
        end = _parse_month_day(cross.group("end_month"), cross.group("end_day"), year)
        return start, end
    same = _SAME_MONTH.search(cleaned)
    if same:
        start = _parse_month_day(same.group("month"), same.group("start_day"), year)
        end = _parse_month_day(same.group("month"), same.group("end_day"), year)
        return start, end
    return None, None


def _season_year_from_page(soup: BeautifulSoup, fallback: int) -> int:
    title = soup.select_one(".wf-title")
    text = title.get_text(" ", strip=True) if title else ""
    match = _YEAR.search(text) or _YEAR.search(soup.title.get_text() if soup.title else "")
    if match:
        return int(match.group(1))
    return fallback


def _parse_event_card(item: Tag, *, season_year: int) -> VctDiscoveredEvent | None:
    href = str(item.get("href") or "")
    href_match = _EVENT_HREF.search(href)
    if href_match is None:
        return None
    event_id = int(href_match.group(1))
    slug = href_match.group(2)
    title = item.select_one(".event-item-title")
    name = title.get_text(" ", strip=True) if title else f"Event {event_id}"
    status_node = item.select_one(".event-item-desc-item-status")
    source_status = status_node.get_text(" ", strip=True) if status_node else None
    dates_node = item.select_one(".event-item-desc-item.mod-dates")
    dates_text = _label_stripped_text(dates_node)
    start_date, end_date = parse_vct_date_range(dates_text, year=season_year)
    flag = item.select_one(".event-item-desc-item.mod-location .flag")
    flag_code = _flag_code(flag)
    status = (
        canonical_event_status(
            source_status,
            start_date=start_date,
            end_date=end_date,
        )
        or EventStatus.UPCOMING
    )
    return VctDiscoveredEvent(
        vlr_event_id=event_id,
        name=name,
        status=status,
        region=vct_region_from_name(name, flag_code=flag_code),
        stage=vct_stage_from_name(name),
        tier="T1",
        circuit=CircuitName.VCT.value,
        season_year=season_year,
        start_date=start_date,
        end_date=end_date,
        slug=slug,
        source_status=source_status,
    )


def _label_stripped_text(node: Tag | None) -> str | None:
    if node is None:
        return None
    clone = BeautifulSoup(str(node), "html.parser").select_one(".event-item-desc-item")
    target = clone if clone is not None else node
    label = target.select_one(".event-item-desc-item-label")
    if label is not None:
        label.extract()
    text = target.get_text(" ", strip=True)
    return text or None


def _flag_code(flag: Tag | None) -> str | None:
    if flag is None:
        return None
    raw_classes = flag.get("class")
    if isinstance(raw_classes, str):
        class_names = [raw_classes]
    elif raw_classes:
        class_names = [str(item) for item in raw_classes]
    else:
        class_names = []
    for text in class_names:
        if text.startswith("mod-") and text not in {"mod-location"}:
            return text.removeprefix("mod-")
    return None


def _parse_month_day(month: str, day: str, year: int) -> date | None:
    for fmt in ("%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(f"{month} {int(day)} {year}", fmt).date()
        except ValueError:
            continue
    return None
