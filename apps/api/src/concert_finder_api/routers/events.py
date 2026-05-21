from __future__ import annotations

from enum import Enum

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()


class EventCategory(str, Enum):
    safe_bet = "safe_bet"
    stretch_pick = "stretch_pick"
    regular = "regular"


class BilledArtist(BaseModel):
    name: str
    billing_position: int   # 0 = headliner
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


@router.get("/", response_model=list[ScoredEvent])
async def list_events(
    spotify_user_id: str = Query(..., description="Spotify user ID from OAuth session"),
    category: EventCategory | None = Query(None, description="Filter by safe_bet | stretch_pick | regular"),
    limit: int = Query(default=50, le=200),
) -> list[ScoredEvent]:
    # TODO:
    #   1. Load UserSession.taste_modes for spotify_user_id from DB
    #   2. Fetch all events in next 60 days with their artists + embeddings
    #   3. Call score_event() for each, filter by category if set
    #   4. Sort by score desc, generate explanations via HF Inference API
    return []


@router.get("/taste-map")
async def taste_map(spotify_user_id: str = Query(...)) -> dict:
    # TODO: UMAP projection of user's top artists + upcoming event artists
    # Returns {user_points: [...], event_points: [...]} for Plotly scatter
    return {"user_points": [], "event_points": []}
