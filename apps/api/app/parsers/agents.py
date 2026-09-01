from __future__ import annotations

AGENT_ROLES: dict[str, str] = {
    "astra": "Controller",
    "breach": "Initiator",
    "brimstone": "Controller",
    "chamber": "Sentinel",
    "clove": "Controller",
    "cypher": "Sentinel",
    "deadlock": "Sentinel",
    "fade": "Initiator",
    "gekko": "Initiator",
    "harbor": "Controller",
    "iso": "Duelist",
    "jett": "Duelist",
    "kay/o": "Initiator",
    "kayo": "Initiator",
    "killjoy": "Sentinel",
    "neon": "Duelist",
    "omen": "Controller",
    "phoenix": "Duelist",
    "raze": "Duelist",
    "reyna": "Duelist",
    "sage": "Sentinel",
    "skye": "Initiator",
    "sova": "Initiator",
    "tejo": "Initiator",
    "viper": "Controller",
    "vyse": "Sentinel",
    "waylay": "Duelist",
    "yoru": "Duelist",
}

_DISPLAY_NAMES: dict[str, str] = {
    "kayo": "KAY/O",
    "kay/o": "KAY/O",
}


def normalize_agent_name(raw_name: str) -> str:
    cleaned = raw_name.strip()
    if not cleaned:
        return "Unknown"
    key = cleaned.lower().replace(" ", "")
    return _DISPLAY_NAMES.get(key, cleaned.title() if cleaned.lower() == cleaned else cleaned)


def agent_role(name: str) -> str:
    key = name.strip().lower().replace(" ", "")
    if key == "kay/o":
        key = "kayo"
    return AGENT_ROLES.get(key, "Unknown")
