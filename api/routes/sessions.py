from pathlib import Path

from fastapi import APIRouter, HTTPException

from api import session_store
from api.models import (
    CreateSessionIn,
    SessionOut,
    session_to_out,
)
from dj_clipper.models.session_model import AnalysisSettings, SessionState

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionOut, status_code=201)
def create_session(body: CreateSessionIn):
    state = SessionState()
    state.video_path = Path(body.video_path)
    state.settings = AnalysisSettings(
        clip_duration=body.clip_duration,
        n_clips=body.n_clips,
        clip_all=body.clip_all,
        manual_timestamps=body.manual_timestamps,
    )
    if body.playlist_path:
        state.playlist_path = Path(body.playlist_path)
    if body.search_root:
        state.search_root = Path(body.search_root)
    if body.output_dir:
        state.output_dir = Path(body.output_dir)

    entry = session_store.create(state)
    return session_to_out(entry)


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: str):
    entry = session_store.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")
    return session_to_out(entry)


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str):
    entry = session_store.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")
    session_store.delete(session_id)
