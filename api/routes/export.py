import asyncio
import json
import queue
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from api import session_store
from api.models import StartExportIn
from api.runners.export import run_export

router = APIRouter(prefix="/sessions", tags=["export"])

_executor = ThreadPoolExecutor(max_workers=2)


@router.post("/{session_id}/export", status_code=202)
def start_export(session_id: str, body: StartExportIn):
    entry = session_store.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")

    entry.state.output_dir = Path(body.output_dir)

    entry.cancel_event.clear()
    while not entry.export_queue.empty():
        try:
            entry.export_queue.get_nowait()
        except queue.Empty:
            break

    _executor.submit(
        run_export,
        entry.state,
        entry.cancel_event,
        entry.export_queue,
    )
    return {"status": "started"}


@router.get("/{session_id}/export/stream")
async def stream_export(session_id: str):
    entry = session_store.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_gen():
        q = entry.export_queue
        while True:
            try:
                event = q.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.1)
                continue

            yield {"data": json.dumps(event)}

            if event.get("done") or event.get("cancelled") or event.get("error"):
                break

    return EventSourceResponse(event_gen())


@router.post("/{session_id}/export/cancel", status_code=202)
def cancel_export(session_id: str):
    entry = session_store.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")
    entry.cancel_event.set()
    return {"status": "cancelling"}
