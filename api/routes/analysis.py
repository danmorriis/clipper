import asyncio
import json
import queue
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from api import session_store
from api.runners.analysis import run_analysis
from api.runners.thumbnail import run_thumbnails

router = APIRouter(prefix="/sessions", tags=["analysis"])

_executor = ThreadPoolExecutor(max_workers=4)


@router.post("/{session_id}/analyze", status_code=202)
def start_analysis(session_id: str):
    entry = session_store.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")

    # Reset state for a fresh run
    entry.cancel_event.clear()
    while not entry.analysis_queue.empty():
        try:
            entry.analysis_queue.get_nowait()
        except queue.Empty:
            break

    _executor.submit(
        run_analysis,
        entry.state,
        entry.cancel_event,
        entry.analysis_queue,
    )
    return {"status": "started"}


@router.get("/{session_id}/analyze/stream")
async def stream_analysis(session_id: str):
    entry = session_store.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_gen():
        q = entry.analysis_queue
        last_ping = asyncio.get_event_loop().time()

        while True:
            try:
                event = q.get_nowait()
            except queue.Empty:
                now = asyncio.get_event_loop().time()
                if now - last_ping >= 15:
                    yield {"comment": "keepalive"}
                    last_ping = now
                await asyncio.sleep(0.1)
                continue

            last_ping = asyncio.get_event_loop().time()
            yield {"data": json.dumps(event)}

            if event.get("done"):
                # Kick off thumbnail generation after successful analysis
                if not event.get("error") and not event.get("cancelled"):
                    _executor.submit(
                        run_thumbnails,
                        entry.state,
                        entry.cancel_event,
                        entry.analysis_queue,
                    )
                break

        # Stream thumbnail_ready events from the same queue
        while True:
            try:
                event = q.get_nowait()
            except queue.Empty:
                now = asyncio.get_event_loop().time()
                if now - last_ping >= 15:
                    yield {"comment": "keepalive"}
                    last_ping = now
                await asyncio.sleep(0.1)
                continue

            last_ping = asyncio.get_event_loop().time()
            yield {"data": json.dumps(event)}

            if "thumbnails_done" in event or event.get("error") or event.get("cancelled"):
                break

    return EventSourceResponse(event_gen())


@router.post("/{session_id}/analyze/cancel", status_code=202)
def cancel_analysis(session_id: str):
    entry = session_store.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")
    entry.cancel_event.set()
    return {"status": "cancelling"}
