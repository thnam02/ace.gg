from __future__ import annotations

import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup, Tag

from app.parsers.agents import agent_role, normalize_agent_name
from app.parsers.numbers import parse_int, parse_optional_float, parse_optional_int
from app.schemas.ingestion import (
    NormalizedAgent,
    NormalizedEvent,
    NormalizedMatchData,
    NormalizedMatchMap,
    NormalizedPlayer,
    NormalizedPlayerMapStats,
    NormalizedTeam,
)

_PLAYER_HREF = re.compile(r"/player/(\d+)", re.IGNORECASE)
_TEAM_HREF = re.compile(r"/team/(\d+)", re.IGNORECASE)
_EVENT_HREF = re.compile(r"/event/(\d+)", re.IGNORECASE)
_MATCH_ID = re.compile(r"(?:vlr\.gg/|/match/|^/)(\d+)")
_BEST_OF = re.compile(r"(?:bo|best of)\s*(\d+)", re.IGNORECASE)

_STAT_HEADERS: dict[str, str] = {
    "r": "vlr_rating",
    "rating": "vlr_rating",
    "acs": "acs",
    "k": "kills",
    "d": "deaths",
    "a": "assists",
    "kast": "kast_pct",
    "adr": "adr",
    "hs%": "headshot_pct",
    "hs": "headshot_pct",
    "fk": "first_kills",
    "fd": "first_deaths",
}

_DEFAULT_STAT_ORDER = (
    "vlr_rating",
    "acs",
    "kills",
    "deaths",
    "assists",
    "plus_minus",
    "kast_pct",
    "adr",
    "headshot_pct",
    "first_kills",
    "first_deaths",
)


class MatchParser:
    """Parse VLR match HTML into normalized match data."""

    def parse(self, html: str, *, match_id: int | None = None) -> NormalizedMatchData:
        if not html or not html.strip():
            raise ValueError("Match HTML is empty")

        soup = BeautifulSoup(html, "html.parser")
        resolved_match_id = match_id or _extract_match_id(soup)
        if resolved_match_id is None:
            raise ValueError("Could not determine VLR match ID")

        team_a, team_b = _parse_teams(soup)
        event = _parse_event(soup)
        series_score = _parse_series_score(soup)
        maps = _parse_maps(soup, team_a, team_b)

        winner_id = _series_winner(team_a, team_b, series_score, maps)
        status = _parse_status(soup, winner_id)

        return NormalizedMatchData(
            vlr_match_id=resolved_match_id,
            event=event,
            team_a=team_a,
            team_b=team_b,
            winner_vlr_team_id=winner_id,
            played_at=_parse_played_at(soup),
            best_of=_parse_best_of(soup),
            status=status,
            maps=maps,
        )


def _as_tag(value: object) -> Tag | None:
    return value if isinstance(value, Tag) else None


def _text(node: Tag | None) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())


def _attr(node: Tag | None, name: str) -> str | None:
    if node is None:
        return None
    value = node.get(name)
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value) if value is not None else None


def _id_from_href(href: str | None, pattern: re.Pattern[str]) -> int | None:
    if not href:
        return None
    match = pattern.search(href)
    return int(match.group(1)) if match else None


def _extract_match_id(soup: BeautifulSoup) -> int | None:
    candidates: list[str] = []
    canonical = _as_tag(soup.find("link", rel="canonical"))
    if canonical is not None:
        href = _attr(canonical, "href")
        if href:
            candidates.append(href)
    og_url = _as_tag(soup.find("meta", attrs={"property": "og:url"}))
    if og_url is not None:
        content = _attr(og_url, "content")
        if content:
            candidates.append(content)

    for value in candidates:
        if any(part in value for part in ("/player/", "/team/", "/event/")):
            continue
        match = _MATCH_ID.search(value)
        if match:
            return int(match.group(1))
    return None


def _parse_teams(soup: BeautifulSoup) -> tuple[NormalizedTeam, NormalizedTeam]:
    links = [
        tag
        for tag in soup.select("a.match-header-link")
        if isinstance(tag, Tag) and _id_from_href(_attr(tag, "href"), _TEAM_HREF)
    ]
    if len(links) < 2:
        links = [
            tag
            for tag in soup.select('a[href*="/team/"]')
            if isinstance(tag, Tag) and tag.find(class_="wf-title-med")
        ]

    teams: list[NormalizedTeam] = []
    seen: set[int] = set()
    for link in links:
        team = _team_from_link(link)
        if team is None or team.vlr_team_id in seen:
            continue
        seen.add(team.vlr_team_id)
        teams.append(team)
        if len(teams) == 2:
            break

    if len(teams) != 2:
        raise ValueError("Match HTML is missing team A/B")
    return teams[0], teams[1]


def _team_from_link(link: Tag) -> NormalizedTeam | None:
    vlr_id = _id_from_href(_attr(link, "href"), _TEAM_HREF)
    if vlr_id is None:
        return None
    name_node = _as_tag(link.find(class_="wf-title-med")) or link
    name = _text(name_node) or f"Team {vlr_id}"
    tag_node = _as_tag(link.find(class_="ge-text-light"))
    tag = _text(tag_node) or _fallback_tag(name)
    return NormalizedTeam(vlr_team_id=vlr_id, name=name, tag=tag[:16])


def _fallback_tag(name: str) -> str:
    compact = re.sub(r"[^A-Za-z0-9]", "", name)
    return (compact[:4] or "TEAM").upper()


def _class_list(node: Tag) -> list[str]:
    value = node.get("class")
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return value.split()
    return []


def _parse_event(soup: BeautifulSoup) -> NormalizedEvent:
    link = _as_tag(soup.select_one("a.match-header-event")) or _as_tag(
        soup.select_one('a[href*="/event/"]')
    )
    vlr_id = _id_from_href(_attr(link, "href"), _EVENT_HREF)
    if link is None or vlr_id is None:
        raise ValueError("Match HTML is missing event")

    name = ""
    for child in link.children if link is not None else []:
        if not isinstance(child, Tag):
            continue
        if "match-header-event-series" in _class_list(child):
            continue
        candidate = _text(child)
        if candidate:
            name = candidate
            break
    if not name:
        name = _text(link)

    return NormalizedEvent(
        vlr_event_id=vlr_id,
        name=name or f"Event {vlr_id}",
        region=None,
        tier=None,
        season_year=_parse_season_year(name),
    )


def _parse_season_year(name: str) -> int | None:
    match = re.search(r"\b(20\d{2})\b", name)
    return int(match.group(1)) if match else None


def _parse_series_score(soup: BeautifulSoup) -> tuple[int | None, int | None]:
    score_root = _as_tag(soup.select_one(".match-header-vs-score"))
    if score_root is None:
        return None, None
    spoiler = _as_tag(score_root.select_one(".js-spoiler")) or score_root
    numbers = [parse_optional_int(part) for part in re.findall(r"\d+", _text(spoiler))]
    if len(numbers) >= 2:
        return numbers[0], numbers[1]
    return None, None


def _parse_best_of(soup: BeautifulSoup) -> int | None:
    for node in soup.select(".match-header-vs-note"):
        match = _BEST_OF.search(_text(_as_tag(node)))
        if match:
            return int(match.group(1))
    match = _BEST_OF.search(_text(_as_tag(soup.select_one(".match-header"))))
    return int(match.group(1)) if match else None


def _parse_status(soup: BeautifulSoup, winner_id: int | None) -> str | None:
    notes = " ".join(_text(_as_tag(node)).lower() for node in soup.select(".match-header-vs-note"))
    if "live" in notes:
        return "live"
    if "upcoming" in notes or "tbd" in notes:
        return "upcoming"
    if "final" in notes or winner_id is not None:
        return "completed"
    return None


def _parse_played_at(soup: BeautifulSoup) -> datetime | None:
    moment = _as_tag(soup.select_one(".moment-tz-convert[data-utc-ts]"))
    timestamp = parse_optional_int(_attr(moment, "data-utc-ts"))
    if timestamp is not None:
        return datetime.fromtimestamp(timestamp, tz=UTC)

    date_node = _as_tag(soup.select_one(".match-header-date"))
    raw = _text(date_node)
    if not raw:
        return None
    for fmt in ("%A, %B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.split("  ")[0], fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _series_winner(
    team_a: NormalizedTeam,
    team_b: NormalizedTeam,
    series_score: tuple[int | None, int | None],
    maps: list[NormalizedMatchMap],
) -> int | None:
    score_a, score_b = series_score
    if score_a is not None and score_b is not None and score_a != score_b:
        return team_a.vlr_team_id if score_a > score_b else team_b.vlr_team_id

    wins_a = sum(1 for item in maps if item.winner_vlr_team_id == team_a.vlr_team_id)
    wins_b = sum(1 for item in maps if item.winner_vlr_team_id == team_b.vlr_team_id)
    if wins_a == wins_b:
        return None
    return team_a.vlr_team_id if wins_a > wins_b else team_b.vlr_team_id


def _parse_maps(
    soup: BeautifulSoup,
    team_a: NormalizedTeam,
    team_b: NormalizedTeam,
) -> list[NormalizedMatchMap]:
    nav_ids = _played_game_ids(soup)
    games = [
        tag
        for tag in soup.select("div.vm-stats-game")
        if isinstance(tag, Tag) and _attr(tag, "data-game-id") not in {None, "all"}
    ]
    if nav_ids:
        by_id = {_attr(game, "data-game-id"): game for game in games}
        games = [by_id[game_id] for game_id in nav_ids if game_id in by_id]

    maps: list[NormalizedMatchMap] = []
    for index, game in enumerate(games, start=1):
        if "not available" in _text(game).lower():
            continue
        parsed = _parse_game(game, index, team_a, team_b)
        if parsed is not None:
            maps.append(parsed)
    return maps


def _played_game_ids(soup: BeautifulSoup) -> list[str]:
    ids: list[str] = []
    for item in soup.select(".vm-stats-gamesnav-item"):
        tag = _as_tag(item)
        if tag is None:
            continue
        classes = _class_list(tag)
        if "mod-disabled" in classes or "mod-all" in classes:
            continue
        game_id = _attr(tag, "data-game-id")
        if not game_id or game_id == "all":
            continue
        ids.append(game_id)
    return ids


def _parse_game(
    game: Tag,
    map_number: int,
    team_a: NormalizedTeam,
    team_b: NormalizedTeam,
) -> NormalizedMatchMap | None:
    map_name = _parse_map_name(game)
    if not map_name:
        return None

    score_a, score_b = _parse_map_scores(game)
    rounds_played = None
    if score_a is not None and score_b is not None:
        rounds_played = score_a + score_b

    winner_id = None
    if score_a is not None and score_b is not None and score_a != score_b:
        winner_id = team_a.vlr_team_id if score_a > score_b else team_b.vlr_team_id

    player_stats: list[NormalizedPlayerMapStats] = []
    tables = [tag for tag in game.select("table.wf-table-inset") if isinstance(tag, Tag)]
    for table_index, table in enumerate(tables[:2]):
        team = _team_for_table(table, table_index, team_a, team_b)
        player_stats.extend(_parse_player_rows(table, team, rounds_played or 0, team_a, team_b))

    return NormalizedMatchMap(
        map_number=map_number,
        map_name=map_name,
        team_a_score=score_a,
        team_b_score=score_b,
        winner_vlr_team_id=winner_id,
        rounds_played=rounds_played,
        player_stats=player_stats,
    )


def _parse_map_name(game: Tag) -> str | None:
    named = _as_tag(game.select_one(".map-name"))
    if named is not None:
        name = _text(named)
        return name.title() if name else None

    map_node = _as_tag(game.select_one(".map"))
    name = _text(map_node)
    name = re.sub(r"\bPICK\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\d+:\d+", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name.title() if name else None


def _parse_map_scores(game: Tag) -> tuple[int | None, int | None]:
    header = _as_tag(game.select_one(".vm-stats-game-header")) or game
    scores = [
        parse_optional_int(_text(_as_tag(node)))
        for node in header.select(".score")
        if isinstance(node, Tag)
    ]
    scores = [score for score in scores if score is not None]
    if len(scores) >= 2:
        return scores[0], scores[1]
    return None, None


def _team_for_table(
    table: Tag,
    table_index: int,
    team_a: NormalizedTeam,
    team_b: NormalizedTeam,
) -> NormalizedTeam:
    header = _text(_as_tag(table.select_one("th.mod-player")))
    for team in (team_a, team_b):
        if header and header.lower() in {team.tag.lower(), team.name.lower()}:
            return team
    first_player = _as_tag(table.select_one("td.mod-player"))
    tag_text = _text(_as_tag(first_player.find(class_="ge-text-light") if first_player else None))
    for team in (team_a, team_b):
        if tag_text and tag_text.lower() == team.tag.lower():
            return team
    return team_a if table_index == 0 else team_b


def _parse_player_rows(
    table: Tag,
    team: NormalizedTeam,
    rounds: int,
    team_a: NormalizedTeam,
    team_b: NormalizedTeam,
) -> list[NormalizedPlayerMapStats]:
    header_map = _header_map(table)
    rows: list[NormalizedPlayerMapStats] = []
    for row in table.select("tbody tr"):
        tag = _as_tag(row)
        if tag is None or tag.select_one("td.mod-player") is None:
            continue
        parsed = _parse_player_row(tag, team, rounds, header_map, team_a, team_b)
        if parsed is not None:
            rows.append(parsed)
    return rows


def _header_map(table: Tag) -> dict[int, str]:
    mapping: dict[int, str] = {}
    headers = [tag for tag in table.select("thead th") if isinstance(tag, Tag)]
    stat_index = 0
    for header in headers:
        classes = _class_list(header)
        if "mod-player" in classes or "mod-agents" in classes:
            continue
        label = _text(header).lower()
        field = _STAT_HEADERS.get(label)
        if field is None and stat_index < len(_DEFAULT_STAT_ORDER):
            field = _DEFAULT_STAT_ORDER[stat_index]
        if field:
            mapping[stat_index] = field
        stat_index += 1
    return mapping


def _parse_player_row(
    row: Tag,
    team: NormalizedTeam,
    rounds: int,
    header_map: dict[int, str],
    team_a: NormalizedTeam,
    team_b: NormalizedTeam,
) -> NormalizedPlayerMapStats | None:
    player_cell = _as_tag(row.select_one("td.mod-player"))
    player = _parse_player(player_cell)
    if player is None:
        return None

    team_vlr_id = team.vlr_team_id
    tag_text = _text(_as_tag(player_cell.find(class_="ge-text-light") if player_cell else None))
    for candidate in (team_a, team_b):
        if tag_text and tag_text.lower() == candidate.tag.lower():
            team_vlr_id = candidate.vlr_team_id
            break

    stats = _parse_stat_cells(row, header_map)
    agent = _parse_agent(row)

    return NormalizedPlayerMapStats(
        player=player,
        team_vlr_id=team_vlr_id,
        agent=agent,
        rounds=rounds,
        kills=parse_int(stats.get("kills")),
        deaths=parse_int(stats.get("deaths")),
        assists=parse_int(stats.get("assists")),
        first_kills=parse_int(stats.get("first_kills")),
        first_deaths=parse_int(stats.get("first_deaths")),
        adr=parse_optional_float(stats.get("adr")),
        kast_pct=parse_optional_float(stats.get("kast_pct")),
        acs=parse_optional_float(stats.get("acs")),
        vlr_rating=parse_optional_float(stats.get("vlr_rating")),
        headshot_pct=parse_optional_float(stats.get("headshot_pct")),
    )


def _parse_player(cell: Tag | None) -> NormalizedPlayer | None:
    if cell is None:
        return None
    link = _as_tag(cell.find("a", href=True))
    vlr_id = _id_from_href(_attr(link, "href"), _PLAYER_HREF)
    if vlr_id is None:
        return None
    handle_node = _as_tag(cell.select_one(".text-of")) or link
    handle = _text(handle_node) or f"Player {vlr_id}"
    flag = _as_tag(cell.select_one("i.flag"))
    country = None
    if flag is not None:
        for class_name in _class_list(flag):
            if class_name.startswith("mod-") and class_name != "mod-dark":
                country = class_name.removeprefix("mod-").upper()
                break
    return NormalizedPlayer(vlr_player_id=vlr_id, handle=handle, country=country)


def _parse_agent(row: Tag) -> NormalizedAgent:
    img = _as_tag(row.select_one("td.mod-agents img"))
    raw = _attr(img, "title") or _attr(img, "alt") or "Unknown"
    name = normalize_agent_name(raw)
    return NormalizedAgent(name=name, role=agent_role(name))


def _parse_stat_cells(row: Tag, header_map: dict[int, str]) -> dict[str, str]:
    cells = [
        tag
        for tag in row.find_all("td", recursive=False)
        if isinstance(tag, Tag)
        and "mod-player" not in _class_list(tag)
        and "mod-agents" not in _class_list(tag)
    ]
    stats: dict[str, str] = {}
    for index, cell in enumerate(cells):
        field = header_map.get(index)
        classes = _class_list(cell)
        if "mod-vlr-kills" in classes:
            field = "kills"
        elif "mod-vlr-deaths" in classes:
            field = "deaths"
        elif "mod-vlr-assists" in classes:
            field = "assists"
        if not field or field == "plus_minus":
            continue
        stats[field] = _stat_cell_text(cell)
    return stats


def _stat_cell_text(cell: Tag) -> str:
    both = _as_tag(cell.select_one(".mod-both, .side.mod-both, span.mod-both"))
    if both is not None:
        return _text(both)
    return _text(cell)
