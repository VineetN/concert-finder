from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

import httpx
import numpy as np
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from concert_finder_api.db import get_session
from concert_finder_ingest.enrichment import SpotifyEnricher
from concert_finder_scoring.embeddings import build_artist_vector
from concert_finder_scoring.taste import compute_taste_modes
from concert_finder_shared.models import Artist, UserSession

log = logging.getLogger(__name__)
router = APIRouter()

SPOTIFY_API = "https://api.spotify.com/v1"
TIME_RANGES = ["short_term", "medium_term", "long_term"]


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


async def _fetch_spotify_data(token: str) -> tuple[dict, list[dict]]:
    """Fetch /me and /me/top/artists across all three time ranges."""
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(headers=headers, timeout=15) as client:
        me = (await client.get(f"{SPOTIFY_API}/me")).raise_for_status().json()

        seen: dict[str, dict] = {}
        for time_range in TIME_RANGES:
            resp = await client.get(
                f"{SPOTIFY_API}/me/top/artists",
                params={"time_range": time_range, "limit": 50},
            )
            resp.raise_for_status()
            for artist in resp.json().get("items", []):
                seen.setdefault(artist["id"], artist)

    return me, list(seen.values())


def _sync_artists(token: str, spotify_artists: list[dict]) -> dict[str, Artist]:
    """
    Upsert artists into DB: create missing ones (with audio features), build
    any missing embeddings. Runs in a thread — uses sync httpx + SQLite.
    """
    enricher = SpotifyEnricher(token)
    try:
        with get_session() as session:
            result: dict[str, Artist] = {}

            for sa in spotify_artists:
                sid = sa["id"]
                artist = session.get(Artist, sid)

                if artist is None:
                    try:
                        audio_feat = enricher.get_audio_features(sid)
                    except Exception:
                        log.warning("Could not fetch audio features for %s", sid)
                        audio_feat = None

                    artist = Artist(
                        id=sid,
                        name=sa["name"],
                        spotify_id=sid,
                        genres=json.dumps(sa.get("genres", [])),
                        popularity=sa.get("popularity"),
                        audio_features=json.dumps(audio_feat) if audio_feat else None,
                        last_enriched=datetime.utcnow(),
                    )
                    session.add(artist)

                if artist.embedding is None:
                    try:
                        vec = build_artist_vector(
                            artist.name,
                            json.loads(artist.genres),
                            json.loads(artist.audio_features) if artist.audio_features else None,
                        )
                        artist.embedding = vec.tobytes()
                        session.add(artist)
                    except Exception:
                        log.warning("Could not build embedding for %s", artist.name)

                result[sid] = artist

            session.commit()
            for a in result.values():
                session.refresh(a)

        return result
    finally:
        enricher.close()


def _upsert_session(
    spotify_id: str,
    display_name: str | None,
    top_ids: list[str],
    taste_mode_map: dict,
) -> None:
    with get_session() as session:
        obj = session.get(UserSession, spotify_id) or UserSession(id=spotify_id)
        obj.display_name = display_name
        obj.top_artist_ids = json.dumps(top_ids)
        obj.taste_modes = json.dumps(taste_mode_map)
        obj.last_synced = datetime.utcnow()
        session.add(obj)
        session.commit()


@router.post("/sync", response_model=UserProfile)
async def sync_user(authorization: str = Header(...)) -> UserProfile:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization.removeprefix("Bearer ")

    try:
        user, spotify_artists = await _fetch_spotify_data(token)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail="Spotify API error",
        ) from exc

    spotify_id = user["id"]
    display_name = user.get("display_name")
    top_ids = [sa["id"] for sa in spotify_artists]

    # Enrich + embed in a thread (sync httpx + SQLite + ML inference)
    artist_map = await asyncio.to_thread(_sync_artists, token, spotify_artists)

    # Cluster into taste modes
    embeddings: dict[str, np.ndarray] = {
        aid: np.frombuffer(a.embedding, dtype=np.float32).copy()
        for aid, a in artist_map.items()
        if a.embedding is not None
    }
    taste_mode_map: dict = {}
    if embeddings:
        taste_mode_map = await asyncio.to_thread(compute_taste_modes, embeddings, top_ids)

    await asyncio.to_thread(_upsert_session, spotify_id, display_name, top_ids, taste_mode_map)

    taste_modes = [
        TasteMode(
            id=mode_id,
            label=mode["label"],
            artist_names=[
                artist_map[aid].name
                for aid in mode["artist_ids"]
                if aid in artist_map
            ],
            is_dominant=mode["is_dominant"],
        )
        for mode_id, mode in taste_mode_map.items()
    ]

    return UserProfile(
        spotify_id=spotify_id,
        display_name=display_name,
        taste_modes=taste_modes,
        top_artist_count=len(top_ids),
    )
