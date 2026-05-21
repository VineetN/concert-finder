from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum

import httpx
import numpy as np
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select

from concert_finder_api.db import get_session
from concert_finder_scoring.match import MatchResult, score_event
from concert_finder_scoring.project import project_to_2d
from concert_finder_shared.models import Artist, Event, EventArtist, UserSession

log = logging.getLogger(__name__)
router = APIRouter()

HF_TOKEN = os.getenv("HF_TOKEN", "")
HF_MODEL = "Qwen/Qwen2.5-72B-Instruct"
HF_URL = f"https://api-inference.huggingface.co/models/{HF_MODEL}/v1/chat/completions"
LOOKAHEAD_DAYS = 60


class EventCategory(str, Enum):
    safe_bet = "safe_bet"
    stretch_pick = "stretch_pick"
    regular = "regular"


class BilledArtist(BaseModel):
    name: str
    billing_position: int
    is_match_driver: bool


class ScoredEvent(BaseModel):
    id: str
    date: str
    venue: str
    artists: list[BilledArtist]
    score: float
    category: EventCategory
    driver_artist: str
    driver_mode: str
    explanation: str | None
    ticket_url: str | None
    price_min: float | None
    price_max: float | None


async def _explain(event: Event, driver_artist: str, driver_mode: str) -> str | None:
    """One-sentence match explanation via HF Inference API. Returns None if unavailable."""
    if not HF_TOKEN:
        return None
    prompt = (
        f"In one sentence, explain why a fan of {driver_mode} music "
        f"would enjoy seeing {driver_artist} at {event.venue}."
    )
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.post(
                HF_URL,
                headers={"Authorization": f"Bearer {HF_TOKEN}"},
                json={
                    "model": HF_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 80,
                    "temperature": 0.7,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        log.warning("HF explanation failed for event %s", event.id)
        return None


async def _maybe_explain(event: Event, match: MatchResult) -> str | None:
    """Only safe_bet / stretch_pick events get LLM explanations."""
    if match.category.value == "regular":
        return None
    return await _explain(event, match.driver_artist, match.driver_mode)


def _load_and_score(
    spotify_user_id: str,
    category_filter: str | None,
    limit: int,
) -> tuple[dict, list[tuple[Event, list, MatchResult]]]:
    """
    Load UserSession + upcoming events, batch-load bills, score and filter.
    Two queries (events, then all bills via IN) — no N+1.
    """
    with get_session() as session:
        user_session = session.get(UserSession, spotify_user_id)
        if not user_session or not user_session.taste_modes:
            return {}, []

        taste_modes = json.loads(user_session.taste_modes)

        now = datetime.utcnow()
        cutoff = now + timedelta(days=LOOKAHEAD_DAYS)
        events = session.exec(
            select(Event)
            .where(Event.date >= now, Event.date <= cutoff)
            .order_by(Event.date)
        ).all()

        if not events:
            return taste_modes, []

        event_ids = [e.id for e in events]
        bill_rows = session.exec(
            select(EventArtist, Artist)
            .join(Artist, Artist.id == EventArtist.artist_id)
            .where(EventArtist.event_id.in_(event_ids))
            .order_by(EventArtist.billing_position)
        ).all()

        bills: dict[str, list] = defaultdict(list)
        for ea, artist in bill_rows:
            bills[ea.event_id].append((ea, artist))

        scored = []
        for event in events:
            bill = bills.get(event.id, [])
            if not bill:
                continue
            match = score_event(event, bill, taste_modes)
            if category_filter is None or match.category.value == category_filter:
                scored.append((event, bill, match))

        scored.sort(key=lambda x: x[2].score, reverse=True)
        return taste_modes, scored[:limit]


async def _resolve_spotify_id(authorization: str) -> str:
    """Resolve Spotify user ID from the Bearer token via Spotify /me."""
    token = authorization.removeprefix("Bearer ").strip()
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.spotify.com/v1/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
    return resp.json()["id"]


@router.get("/events", response_model=list[ScoredEvent])
async def list_events(
    authorization: str = Header(...),
    category: EventCategory | None = Query(None, description="Filter by safe_bet | stretch_pick | regular"),
    limit: int = Query(default=50, le=200),
) -> list[ScoredEvent]:
    try:
        spotify_user_id = await _resolve_spotify_id(authorization)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail="Spotify token invalid") from exc

    category_filter = category.value if category else None
    taste_modes, scored = await asyncio.to_thread(
        _load_and_score, spotify_user_id, category_filter, limit
    )

    if not taste_modes:
        raise HTTPException(status_code=404, detail="User not synced — call POST /user/sync first")

    explanations: list[str | None] = list(
        await asyncio.gather(*[_maybe_explain(event, match) for event, _, match in scored])
    )

    return [
        ScoredEvent(
            id=event.id,
            date=event.date.isoformat(),
            venue=event.venue,
            artists=[
                BilledArtist(
                    name=artist.name,
                    billing_position=ea.billing_position,
                    is_match_driver=(artist.name == match.driver_artist),
                )
                for ea, artist in bill
            ],
            score=match.score,
            category=EventCategory(match.category.value),
            driver_artist=match.driver_artist,
            driver_mode=match.driver_mode,
            explanation=explanation,
            ticket_url=event.ticket_url,
            price_min=event.price_min,
            price_max=event.price_max,
        )
        for (event, bill, match), explanation in zip(scored, explanations)
    ]


class TasteMapUserArtist(BaseModel):
    id: str
    name: str
    x: float
    y: float
    mode_id: str
    mode_label: str
    is_dominant: bool


class TasteMapEventArtist(BaseModel):
    id: str
    name: str
    x: float
    y: float
    event_id: str
    venue: str
    date: str  # ISO-8601


class TasteMapResponse(BaseModel):
    user_artists: list[TasteMapUserArtist]
    event_artists: list[TasteMapEventArtist]


def _compute_taste_map(spotify_user_id: str) -> TasteMapResponse | None:
    """
    Load embeddings for the user's top artists + upcoming event headliners,
    run a combined UMAP projection, and return structured 2-D coordinates.

    Runs in a thread (called via asyncio.to_thread) — uses sync SQLite session.
    """
    with get_session() as session:
        user_session = session.get(UserSession, spotify_user_id)
        if not user_session or not user_session.taste_modes:
            return None

        taste_modes: dict = json.loads(user_session.taste_modes)
        top_artist_ids: list[str] = json.loads(user_session.top_artist_ids)

        # ── User's top artists ────────────────────────────────────────────────
        user_artists_db = session.exec(
            select(Artist).where(Artist.id.in_(top_artist_ids))
        ).all()
        user_art_map: dict[str, Artist] = {
            a.id: a for a in user_artists_db if a.embedding
        }

        # ── Upcoming event headliners (billing_position == 0) ────────────────
        now = datetime.utcnow()
        cutoff = now + timedelta(days=LOOKAHEAD_DAYS)
        event_rows = session.exec(
            select(Event, EventArtist, Artist)
            .join(EventArtist, EventArtist.event_id == Event.id)
            .join(Artist, Artist.id == EventArtist.artist_id)
            .where(Event.date >= now, Event.date <= cutoff)
            .where(EventArtist.billing_position == 0)
        ).all()

        # ── Build combined embedding dict keyed by namespaced string ─────────
        # "u:<artist_id>"          → user top artist
        # "e:<artist_id>:<event_id>" → event headliner
        all_embeddings: dict[str, np.ndarray] = {}
        for aid, a in user_art_map.items():
            all_embeddings[f"u:{aid}"] = np.frombuffer(a.embedding, dtype=np.float32).copy()  # type: ignore[arg-type]

        event_meta: dict[str, tuple[Event, Artist]] = {}
        for event, _ea, artist in event_rows:
            if artist.embedding:
                key = f"e:{artist.id}:{event.id}"
                all_embeddings[key] = np.frombuffer(artist.embedding, dtype=np.float32).copy()
                event_meta[key] = (event, artist)

        if not all_embeddings:
            return TasteMapResponse(user_artists=[], event_artists=[])

        # ── UMAP / PCA projection (combined, so relative distances are meaningful) ─
        coords = project_to_2d(all_embeddings)

        # ── artist_id → (mode_id, mode_label, is_dominant) ───────────────────
        artist_mode: dict[str, tuple[str, str, bool]] = {}
        for mode_id, mode in taste_modes.items():
            label = mode.get("label", mode_id)
            dominant = bool(mode.get("is_dominant", False))
            for aid in mode.get("artist_ids", []):
                artist_mode[aid] = (mode_id, label, dominant)

        # ── Assemble response ─────────────────────────────────────────────────
        user_points: list[TasteMapUserArtist] = []
        for aid, artist in user_art_map.items():
            key = f"u:{aid}"
            if key not in coords:
                continue
            x, y = coords[key]
            mode_id, mode_label, is_dominant = artist_mode.get(aid, ("?", "unknown", False))
            user_points.append(TasteMapUserArtist(
                id=aid, name=artist.name,
                x=round(x, 4), y=round(y, 4),
                mode_id=mode_id, mode_label=mode_label,
                is_dominant=is_dominant,
            ))

        event_points: list[TasteMapEventArtist] = []
        seen_event_artists: set[str] = set()
        for key, (event, artist) in event_meta.items():
            if key not in coords:
                continue
            dedup_key = f"{artist.id}:{event.id}"
            if dedup_key in seen_event_artists:
                continue
            seen_event_artists.add(dedup_key)
            x, y = coords[key]
            event_points.append(TasteMapEventArtist(
                id=artist.id, name=artist.name,
                x=round(x, 4), y=round(y, 4),
                event_id=event.id, venue=event.venue,
                date=event.date.isoformat(),
            ))

        return TasteMapResponse(user_artists=user_points, event_artists=event_points)


@router.get("/events/taste-map", response_model=TasteMapResponse)
async def taste_map(authorization: str = Header(...)) -> TasteMapResponse:
    """
    UMAP projection of the user's top artists + upcoming event headliners.
    User points are coloured by taste-mode cluster; event diamonds show
    spatial proximity to the user's taste modes.
    """
    try:
        spotify_user_id = await _resolve_spotify_id(authorization)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail="Spotify token invalid",
        ) from exc

    result = await asyncio.to_thread(_compute_taste_map, spotify_user_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="User not synced — call POST /user/sync first",
        )
    return result
