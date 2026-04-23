"""
DJ Clipper FastAPI application.

Start with:
  uvicorn api.main:app --host 127.0.0.1 --port 9001 --reload
Or via environment variable:
  DJ_CLIPPER_PORT=9001 uvicorn api.main:app --host 127.0.0.1 --port $DJ_CLIPPER_PORT
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import analysis, candidates, export, files, persist, sessions

app = FastAPI(title="DJ Clipper API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Electron renderer runs on file:// or localhost
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(analysis.router)
app.include_router(candidates.router)
app.include_router(export.router)
app.include_router(files.router)
app.include_router(persist.router)


@app.get("/healthz")
def health():
    return {"status": "ok"}
