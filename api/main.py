"""
DJ Clipper FastAPI application.

Start with:
  uvicorn api.main:app --host 127.0.0.1 --port 9001 --reload
Or via environment variable:
  DJ_CLIPPER_PORT=9001 uvicorn api.main:app --host 127.0.0.1 --port $DJ_CLIPPER_PORT
"""

import os
import sys

# ── Beta expiry check ──────────────────────────────────────────────────────────
# Only active in packaged builds (token is only set when spawned by Electron).
_BETA_EXPIRY_STR = "2026-05-08"

def _marker_path():
    """Platform-appropriate path for the high-water mark file."""
    from pathlib import Path
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Clip Lab"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / "Clip Lab"
    else:
        base = Path.home() / ".cliplab"
    base.mkdir(parents=True, exist_ok=True)
    return base / ".beta_hwm"   # hidden high-water mark file

def _get_network_date():
    """Return today's date from the internet. Falls back to None on failure."""
    from datetime import date
    import json, urllib.request
    # Primary: WorldTimeAPI
    try:
        with urllib.request.urlopen("http://worldtimeapi.org/api/ip", timeout=5) as r:
            return date.fromisoformat(json.loads(r.read())["datetime"][:10])
    except Exception:
        pass
    # Fallback: HTTP Date header from Google
    try:
        from email.utils import parsedate
        with urllib.request.urlopen("https://www.google.com", timeout=5) as r:
            t = parsedate(r.headers.get("Date", ""))
            if t:
                return date(t[0], t[1], t[2])
    except Exception:
        pass
    return None   # could not reach internet

def _effective_date():
    """
    Returns the highest date ever observed — prevents clock-rollback bypass.
    Sources: internet > local clock > stored high-water mark.
    We persist whichever is highest so the app can never see an earlier date
    than it has already recorded, even if the clock is rolled back or
    internet is blocked.
    """
    from datetime import date
    local   = date.today()
    network = _get_network_date()
    marker  = _marker_path()

    stored = date.min
    try:
        stored = date.fromisoformat(marker.read_text().strip())
    except Exception:
        pass

    effective = max(d for d in [local, network, stored] if d is not None)

    try:
        marker.write_text(effective.isoformat())
    except Exception:
        pass

    return effective

if os.environ.get("DJ_CLIPPER_TOKEN"):   # only enforce in packaged builds
    from datetime import date as _date
    _expiry = _date.fromisoformat(_BETA_EXPIRY_STR)
    if _effective_date() > _expiry:
        print("BETA_EXPIRED", flush=True)
        sys.exit(0)
# ──────────────────────────────────────────────────────────────────────────────

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

from api.routes import analysis, candidates, export, files, persist, sessions

app = FastAPI(title="DJ Clipper API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Electron renderer runs on file:// or localhost
    allow_methods=["*"],
    allow_headers=["*", "X-Clipper-Token"],
)

_EXEMPT = {"/healthz"}


class TokenAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _EXEMPT or request.method == "OPTIONS":
            return await call_next(request)
        expected = os.environ.get("DJ_CLIPPER_TOKEN", "")
        if not expected:
            # Running without Electron (e.g. direct uvicorn in dev) — pass through
            return await call_next(request)
        # Accept token from header (fetch/XHR) or query param (img/video src)
        provided = (
            request.headers.get("X-Clipper-Token", "")
            or request.query_params.get("token", "")
        )
        if provided != expected:
            return Response("Forbidden", status_code=403)
        return await call_next(request)


app.add_middleware(TokenAuthMiddleware)

app.include_router(sessions.router)
app.include_router(analysis.router)
app.include_router(candidates.router)
app.include_router(export.router)
app.include_router(files.router)
app.include_router(persist.router)


@app.get("/healthz")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import sys
    import uvicorn

    host = "127.0.0.1"
    port = int(os.environ.get("DJ_CLIPPER_PORT", "9001"))

    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--host" and i + 1 < len(args):
            host = args[i + 1]
        elif arg == "--port" and i + 1 < len(args):
            port = int(args[i + 1])

    uvicorn.run(app, host=host, port=port)
