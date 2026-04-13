"""Loads scheme JSONs, ambiguity map, prerequisites, and documents from data/."""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
SCHEMES_DIR = DATA_DIR / "schemes"


def load_scheme(scheme_id: str) -> dict:
    """Load a single scheme JSON by scheme_id."""
    path = SCHEMES_DIR / f"{scheme_id}.json"
    with open(path) as f:
        return json.load(f)


def load_all_schemes() -> list[dict]:
    """Load all scheme JSONs from data/schemes/."""
    return [json.loads(p.read_text()) for p in sorted(SCHEMES_DIR.glob("*.json"))]


def load_prerequisites() -> dict:
    """Load prerequisite DAG edges."""
    with open(DATA_DIR / "prerequisites.json") as f:
        return json.load(f)


def load_ambiguity_map() -> list[dict]:
    """Load ambiguity annotations."""
    with open(DATA_DIR / "ambiguity_map.json") as f:
        return json.load(f)


def load_documents() -> dict:
    """Load document checklist data."""
    with open(DATA_DIR / "documents.json") as f:
        return json.load(f)
