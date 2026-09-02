from __future__ import annotations

from pathlib import Path
from typing import Any

JSON_ROOT = Path(__file__).parent / "fixtures" / "vlrggapi"


def load_json(name: str) -> dict[str, Any]:
    import json

    return json.loads((JSON_ROOT / name).read_text(encoding="utf-8"))


def _player_row(
    player_id: int,
    name: str,
    agent: str,
    *,
    kills: str = "10",
    deaths: str = "10",
    rounds: str = "21",
    acs: str | None = "220",
    adr: str | None = "150",
    kast: str | None = "70%",
    rating: str | None = "1.0",
    hs_pct: str | None = "25%",
    fk: str = "2",
    fd: str = "2",
) -> dict[str, str]:
    row: dict[str, str] = {
        "id": str(player_id),
        "name": name,
        "agent": agent,
        "kills": kills,
        "deaths": deaths,
        "assists": "3",
        "rounds": rounds,
        "fk": fk,
        "fd": fd,
    }
    if acs is not None:
        row["acs"] = acs
    if adr is not None:
        row["adr"] = adr
    if kast is not None:
        row["kast"] = kast
    if rating is not None:
        row["rating"] = rating
    if hs_pct is not None:
        row["hs_pct"] = hs_pct
    return row


def event_91000() -> dict[str, Any]:
    return {
        "segments": {
            "event": {
                "name": "Champions 2024",
                "series": "Valorant Champions Tour 2024",
                "dates": "Aug 1 - Aug 25, 2024",
                "location": "Los Angeles, USA",
            },
            "teams": [
                {
                    "id": "91001",
                    "name": "Sentinels",
                    "players": [
                        {"id": "92001", "name": "TenZ"},
                        {"id": "92002", "name": "zekken"},
                        {"id": "92003", "name": "sacy"},
                        {"id": "92004", "name": "pancada"},
                        {"id": "92005", "name": "johnqt"},
                    ],
                },
                {
                    "id": "91002",
                    "name": "LOUD",
                    "players": [
                        {"id": "92006", "name": "aspas"},
                        {"id": "92007", "name": "cauanzin"},
                        {"id": "92008", "name": "tuyz"},
                        {"id": "92009", "name": "saadhak"},
                        {"id": "92010", "name": "less"},
                    ],
                },
            ],
        }
    }


def event_91000_matches() -> dict[str, Any]:
    return {
        "matches": [
            {"match_id": "900001"},
            {"match_id": "900001"},
            {"match_id": "900002"},
            {"match_id": "999999"},
            {"match_id": "999998"},
        ]
    }


def match_900001_bo3() -> dict[str, Any]:
    sen_players = [
        _player_row(92001, "TenZ", "Jett", kills="18", rating="1.31", acs="248"),
        _player_row(92002, "zekken", "Raze"),
        _player_row(92003, "sacy", "Sova"),
        _player_row(92004, "pancada", "Omen"),
        _player_row(92005, "johnqt", "Cypher"),
    ]
    loud_players = [
        _player_row(92006, "aspas", "Jett"),
        _player_row(92007, "cauanzin", "Gekko"),
        _player_row(92008, "tuyz", "Fade"),
        _player_row(92009, "saadhak", "Harbor"),
        _player_row(92010, "less", "Killjoy"),
    ]
    return {
        "match_id": "900001",
        "event": {"name": "Champions 2024", "series": "Playoffs: Grand Final"},
        "date": "August 10, 2024",
        "status": "completed",
        "map_vetos": "Bo3",
        "teams": [
            {"id": "91001", "name": "Sentinels", "score": 2},
            {"id": "91002", "name": "LOUD", "score": 0},
        ],
        "maps": [
            {
                "map_name": "Bind",
                "score": {
                    "team1": {"total": 13},
                    "team2": {"total": 8},
                },
                "players": {"team1": sen_players, "team2": loud_players},
            },
            {
                "map_name": "Haven",
                "score": {
                    "team1": {"total": 13},
                    "team2": {"total": 9},
                },
                "players": {"team1": sen_players, "team2": loud_players},
            },
        ],
        "performance": {
            "advanced_stats": [
                {"player": "TenZ", "clutch_1v1": "1", "5K": "0"},
            ]
        },
    }


def match_900002_bo1() -> dict[str, Any]:
    geng_players = [
        _player_row(93001, "t3xture", "Raze"),
        _player_row(93002, "meteor", "Gekko"),
        _player_row(93003, "karon", "Sova"),
        _player_row(93004, "Munchkin", "Omen"),
        _player_row(93005, "Lakia", "Cypher"),
    ]
    prx_players = [
        _player_row(93006, "something", "Jett"),
        _player_row(93007, "f0rsakeN", "Fade"),
        _player_row(93008, "d4v41", "Breach"),
        _player_row(93009, "mindfreak", "Viper"),
        _player_row(93010, "Jinggg", "Raze"),
    ]
    return {
        "match_id": "900002",
        "event": {"name": "Champions 2024", "series": "Playoffs"},
        "date": "August 11, 2024",
        "status": "completed",
        "teams": [
            {"id": "92001", "name": "Gen.G", "score": 1},
            {"id": "92002", "name": "Paper Rex", "score": 0},
        ],
        "maps": [
            {
                "map_name": "Sunset",
                "score": {"team1": {"total": 13}, "team2": {"total": 10}},
                "players": {"team1": geng_players, "team2": prx_players},
            }
        ],
    }


def match_900003_sparse() -> dict[str, Any]:
    return {
        "match_id": "900003",
        "event": {"name": "LOCK//IN Sao Paulo", "series": "Group Stage"},
        "date": "March 3, 2024",
        "status": "completed",
        "teams": [
            {"id": "93001", "name": "NRG", "score": 1},
            {"id": "93002", "name": "FNATIC", "score": 0},
        ],
        "maps": [
            {
                "map_name": "Lotus",
                "score": {"team1": {"total": 13}, "team2": {"total": 7}},
                "players": {
                    "team1": [
                        _player_row(
                            94004,
                            "Ethan",
                            "unknown",
                            acs=None,
                            adr=None,
                            kast=None,
                            rating=None,
                            hs_pct=None,
                            fk="0",
                            fd="0",
                        )
                    ],
                    "team2": [
                        _player_row(94005, "Boaster", "Brimstone", acs=None, adr=None, kast=None),
                    ],
                },
            }
        ],
    }


def match_999998_malformed() -> dict[str, Any]:
    return {"match_id": "999998", "teams": []}
