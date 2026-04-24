"""
DJ Clipper FastAPI application.

Start with:
  uvicorn api.main:app --host 127.0.0.1 --port 9001 --reload
Or via environment variable:
  DJ_CLIPPER_PORT=9001 uvicorn api.main:app --host 127.0.0.1 --port $DJ_CLIPPER_PORT
"""

import os

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
