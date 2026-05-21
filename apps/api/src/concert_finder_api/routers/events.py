from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select

from concert_finder_api.db import get_session
from concert_finder_scoring.match import MatchResult, score_event
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
    """Skip explanation for regular events — only safe_bet / stretch_pick get them."""
    if match.category.value == "regular":
        return None
    return await _explain(event, match.driver_artist, match.driver_mode)


def _load_and_score(
    spotify_user_id: str,
    category_filter: str | None,
    limit: int,
) -> tuple[dict, list[tuple[Event, list, MatchResult]]]:
    """
    Sync: load UserSession + upcoming events, batch-load bills, score and filter.
    Two queries total (events, then all bills via IN) — no N+1.
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


@router.get("/", response_model=list[ScoredEvent])
async def list_events(
    spotify_user_id: str = Query(..., description="Spotify user ID from OAuth session"),
    category: EventCategory | None = Query(None, description="Filter by safe_bet | stretch_pick | regular"),
    limit: int = Query(default=50, le=200),
) -> list[ScoredEvent]:
    category_filter = category.value if category else None
    taste_modes, scored = await asyncio.to_thread(
        _load_and_score, spotify_user_id, category_filter, limit
    )

    if not taste_modes:
        raise HTTPException(status_code=404, detail="User not synced — call POST /user/sync first")

    # Generate explanations in parallel; regular events get None without an API call
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


@router.get("/taste-map")
async def taste_map(spotify_user_id: str = Query(...)) -> dict:
    # TODO: UMAP projection of user's top artists + upcoming event artists
    # Returns {user_points: [...], event_points: [...]} for Plotly scatter
    return {"user_points": [], "event_points": []}
