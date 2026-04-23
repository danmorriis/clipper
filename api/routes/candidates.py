from typing import List

from fastapi import APIRouter, HTTPException

from api import session_store
from api.models import AddManualClipIn, ClipCandidateOut, PatchCandidateIn, candidate_to_out
from dj_clipper.models.clip_model import ClipCandidate

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

    return candidate_to_out(new_clip)


@router.post("/{session_id}/generate-more", response_model=List[ClipCandidateOut])
def generate_more(session_id: str, count: int = 5):
    """
    Surface the next batch of clips from all_candidates pool.
    Returns the newly added candidates (they are appended to session.candidates).
    """
    entry = session_store.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")

    state = entry.state
    pool = state.all_candidates
    idx = entry.next_all_idx
    current_ranks = {c.transition_peak_time for c in state.candidates}

    added = []
    while len(added) < count and idx < len(pool):
        candidate = pool[idx]
        idx += 1
        if candidate.transition_peak_time not in current_ranks:
            current_ranks.add(candidate.transition_peak_time)
            added.append(candidate)

    entry.next_all_idx = idx
    state.candidates.extend(added)
    state.candidates.sort(key=lambda c: c.start_time)
    for i, c in enumerate(state.candidates, 1):
        c.rank = i

    return [candidate_to_out(c) for c in added]
