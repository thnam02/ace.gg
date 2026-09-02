from pathlib import Path

FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "vlr"
MATCHES_DIR = FIXTURES_ROOT / "matches"
EVENTS_DIR = FIXTURES_ROOT / "events"


def fixture_path(name: str) -> Path:
    return MATCHES_DIR / name


def load_match_html(name: str) -> str:
    return fixture_path(name).read_text(encoding="utf-8")


def match_fixture_names() -> list[str]:
    return sorted(path.name for path in MATCHES_DIR.glob("*.html"))


def load_event_html(name: str) -> str:
    return (EVENTS_DIR / name).read_text(encoding="utf-8")


def event_fixture_names() -> list[str]:
    return sorted(path.name for path in EVENTS_DIR.glob("*.html"))
