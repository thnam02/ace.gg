from __future__ import annotations

UNKNOWN_AGENT_NAME = "Unknown"

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


def agent_lookup_key(raw_name: str) -> str:
    return raw_name.strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def _canonical_display(key: str) -> str:
    if key in _DISPLAY_NAMES:
        return _DISPLAY_NAMES[key]
    return key.title()


def is_known_agent(raw_name: str) -> bool:
    key = agent_lookup_key(raw_name)
    if not key or key == "unknown":
        return False
    return key in AGENT_ROLES or key in _DISPLAY_NAMES


def canonical_agent_name(raw_name: str) -> str:
    cleaned = raw_name.strip()
    if not cleaned:
        return UNKNOWN_AGENT_NAME
    key = agent_lookup_key(cleaned)
    if key == "unknown" or not is_known_agent(cleaned):
        return UNKNOWN_AGENT_NAME
    return _canonical_display(key)


def normalize_agent_name(raw_name: str) -> str:
    return canonical_agent_name(raw_name)


def agent_role(name: str) -> str:
    key = agent_lookup_key(name)
    if key == "kay/o":
        key = "kayo"
    return AGENT_ROLES.get(key, UNKNOWN_AGENT_NAME)
