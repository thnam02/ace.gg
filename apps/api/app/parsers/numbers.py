from __future__ import annotations

import re

_NON_NUMERIC = re.compile(r"[^\d.\-]+")


def parse_optional_float(value: object | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)

    cleaned = str(value).replace("%", "").replace(",", "").strip()
    cleaned = cleaned.replace("\xa0", " ")
    if not cleaned or cleaned in {"-", "–", "—", "N/A", "n/a", "TBD"}:
        return None

    token = cleaned.split()[0]
    token = _NON_NUMERIC.sub("", token)
    if not token or token in {"-", "."}:
        return None
    try:
        return float(token)
    except ValueError:
        return None


def parse_optional_int(value: object | None) -> int | None:
    number = parse_optional_float(value)
    if number is None:
        return None
    return int(number)


def parse_int(value: object | None, default: int = 0) -> int:
    parsed = parse_optional_int(value)
    return default if parsed is None else parsed
