"""
Persistence routes for settings that survive app restarts
(replaces QSettings used in the PyQt6 app).
"""

import json
from pathlib import Path

from fastapi import APIRouter

from api.models import SearchRootIn

router = APIRouter(prefix="/persist", tags=["persist"])

_SETTINGS_FILE = Path.home() / ".dj_clipper_settings.json"


def _load() -> dict:
    if _SETTINGS_FILE.exists():
        try:
            return json.loads(_SETTINGS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save(data: dict) -> None:
    _SETTINGS_FILE.write_text(json.dumps(data))


@router.get("/search-root")
def get_search_root():
    return {"path": _load().get("search_root", "")}


@router.put("/search-root")
def set_search_root(body: SearchRootIn):
    data = _load()
    data["search_root"] = body.path
    _save(data)
    return {"path": body.path}
