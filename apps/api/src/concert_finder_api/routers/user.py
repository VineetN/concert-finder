from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class TasteMode(BaseModel):
    id: str
    label: str
    artist_names: list[str]
    is_dominant: bool


class UserProfile(BaseModel):
    spotify_id: str
    display_name: str | None
    taste_modes: list[TasteMode]
    top_artist_count: int


@router.post("/sync", response_model=UserProfile)
async def sync_user(spotify_access_token: str) -> UserProfile:
    # TODO:
    #   1. Call Spotify /me/top/artists for short/medium/long_term
    #   2. Enrich any artists missing from DB
    #   3. Build embeddings, run compute_taste_modes()
    #   4. Upsert UserSession to DB
    #   5. Return profile
    raise NotImplementedError
