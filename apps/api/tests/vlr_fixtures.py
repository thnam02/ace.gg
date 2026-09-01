from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "vlr" / "matches"


def fixture_path(name: str) -> Path:
    return FIXTURES_DIR / name


def load_match_html(name: str) -> str:
    return fixture_path(name).read_text(encoding="utf-8")


def match_fixture_names() -> list[str]:
    return sorted(path.name for path in FIXTURES_DIR.glob("*.html"))
