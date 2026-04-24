from typing import List, Optional

from fastapi import APIRouter, HTTPException

from api import session_store
from api.models import AddManualClipIn, ClipCandidateOut, GenerateMoreOut, PatchCandidateIn, candidate_to_out
from dj_clipper.config import THUMBNAIL_SEEK_OFFSET
from dj_clipper.core.clip_exporter import extract_thumbnail
from dj_clipper.models.clip_model import ClipCandidate


def _generate_thumbnails(state, candidates: list) -> None:
    """Generate thumbnails synchronously for a small batch of candidates."""
    thumb_dir = state.session_temp_dir / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    for candidate in candidates:
        try:
            seek_time = candidate.start_time + THUMBNAIL_SEEK_OFFSET
            thumb_path = thumb_dir / f"thumb_{candidate.rank:03d}.jpg"
            extract_thumbnail(
                video_path=state.video_path,
                time_seconds=seek_time,
                output_path=thumb_path,
            )
            candidate.thumbnail_path = thumb_path
        except Exception:
            pass

router = APIRouter(prefix="/sessions", tags=["candidates"])


@router.get("/{session_id}/candidates", response_model=List[ClipCandidateOut])
def list_candidates(session_id: str):
    entry = session_store.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")
    return [candidate_to_out(c) for c in entry.state.candidates]


@router.patch("/{session_id}/candidates/{rank}", response_model=ClipCandidateOut)
def patch_candidate(session_id: str, rank: int, body: PatchCandidateIn):
    entry = session_store.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")

    candidate = next((c for c in entry.state.candidates if c.rank == rank), None)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if body.kept is not None:
        candidate.kept = body.kept
    if body.pre_track is not None:
        candidate.pre_track = body.pre_track
    if body.post_track is not None:
        candidate.post_track = body.post_track
    if body.start_time is not None:
        candidate.start_time = body.start_time
    if body.end_time is not None:
        candidate.end_time = body.end_time

    return candidate_to_out(candidate)


@router.post("/{session_id}/candidates", response_model=ClipCandidateOut, status_code=201)
def add_manual_clip(session_id: str, body: AddManualClipIn):
    entry = session_store.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")

    candidates = entry.state.candidates
    next_rank = max((c.rank for c in candidates), default=0) + 1
    duration = body.end_time - body.start_time
    mid = (body.start_time + body.end_time) / 2.0

    new_clip = ClipCandidate(
        rank=next_rank,
        start_time=body.start_time,
        end_time=body.end_time,
        transition_peak_time=mid,
        score=1.0,
        is_manual=True,
        pre_track=body.pre_track,
        post_track=body.post_track,
    )
    candidates.append(new_clip)
    candidates.sort(key=lambda c: c.start_time)
    # Re-rank after sort
    for i, c in enumerate(candidates, 1):
        c.rank = i

    _generate_thumbnails(entry.state, [new_clip])

    return candidate_to_out(new_clip)


@router.post("/{session_id}/generate-more", response_model=GenerateMoreOut)
def generate_more(session_id: str, count: int = 5):
    """
    Surface the next batch of clips from all_candidates pool.
    Returns the newly added candidates and the updated next_all_idx so the
    frontend can update only that field without a full session refresh.
    """
    entry = session_store.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")

    state = entry.state
    pool = state.all_candidates
    idx = entry.next_all_idx
    current_peaks = {c.transition_peak_time for c in state.candidates}

    added = []
    while len(added) < count and idx < len(pool):
        candidate = pool[idx]
        idx += 1
        if candidate.transition_peak_time not in current_peaks:
            current_peaks.add(candidate.transition_peak_time)
            added.append(candidate)

    entry.next_all_idx = idx
    state.candidates.extend(added)
    state.candidates.sort(key=lambda c: c.start_time)
    for i, c in enumerate(state.candidates, 1):
        c.rank = i

    if added:
        _generate_thumbnails(entry.state, added)

    return GenerateMoreOut(
        candidates=[candidate_to_out(c) for c in added],
        next_all_idx=entry.next_all_idx,
    )


@router.get("/{session_id}/identify-at")
def identify_at(
    session_id: str,
    t: float,
    side: Optional[str] = None,          # 'pre' or 'post'
    hint_track: Optional[str] = None,
    hint_position: Optional[str] = None,  # 'pre' or 'post'
):
    """
    Identify the track playing at timestamp t.

    Primary: if the session has a stored fingerprint timeline and `side` is
    provided, use confirm_track_near to find the closest confirmed pair of
    adjacent timeline samples on the relevant side of t — this is the most
    reliable approach since the timeline was already fingerprinted at analysis
    time.

    Secondary: live fpcalc fingerprint of the 20 s window around t, compared
    against the full index.

    Fallback: targeted neighbour search using hint_track/hint_position (the
    track on the opposite side of the transition), which constrains the search
    to the expected adjacent playlist entry with a relaxed threshold.
    """
    import json
    from dj_clipper.core.fingerprint_db import fpcalc_piped, query_clip_preloaded
    from dj_clipper.core.transition_finder import confirm_track_near

    entry = session_store.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")

    state = entry.state
    if not state.wav_path or not state.wav_path.exists():
        return {"track": None, "confidence": 0.0}
    if not state.db_path or not state.db_path.exists():
        return {"track": None, "confidence": 0.0}

    # ── Primary: timeline-based pair confirmation ─────────────────────────────
    if side and state.timeline:
        track, confidence = confirm_track_near(state.timeline, t, side)
        if track is not None:
            return {"track": track, "confidence": round(confidence, 3)}

    # ── Secondary: live fpcalc fingerprint ───────────────────────────────────
    index = json.loads(state.db_path.read_text())
    sample_start = max(0.0, t - 10.0)
    fp = fpcalc_piped(state.wav_path, sample_start, 20.0)
    if not fp:
        return {"track": None, "confidence": 0.0}

    matches = query_clip_preloaded(fp, index, min_similarity=0.55)
    if matches:
        return {"track": matches[0].track_name, "confidence": round(matches[0].confidence, 3)}

    # ── Fallback: targeted neighbour search ───────────────────────────────────
    if hint_track and hint_position and state.resolved_track_names:
        names = state.resolved_track_names
        if hint_track in names:
            idx = names.index(hint_track)
            neighbor = None
            if hint_position == "post" and idx > 0:
                neighbor = names[idx - 1]
            elif hint_position == "pre" and idx < len(names) - 1:
                neighbor = names[idx + 1]

            if neighbor and neighbor in index:
                targeted = query_clip_preloaded(
                    fp,
                    {neighbor: index[neighbor]},
                    min_similarity=0.45,
                )
                if targeted:
                    return {"track": targeted[0].track_name, "confidence": round(targeted[0].confidence, 3)}

    return {"track": None, "confidence": 0.0}
