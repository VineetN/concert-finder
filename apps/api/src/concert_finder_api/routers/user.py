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

# Recency weights per time range. short_term = last ~4 weeks; long_term = ~6 months.
# These flow into compute_taste_modes() where they influence centroid position
# and dominance ranking — a recent heavy phase carries more weight than an
# older habit even if the older habit has more unique artists.
TIME_RANGE_WEIGHTS: dict[str, float] = {
    "short_term": 1.0,
    "medium_term": 0.6,
    "long_term": 0.3,
}


class _NumpyEncoder(json.JSONEncoder):
    """Convert numpy scalars/arrays to plain Python types for json.dumps."""
    def default(self, obj: object) -> object:
        if hasattr(obj, "item"):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


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


async def _fetch_spotify_data(
    token: str,
) -> tuple[dict, list[dict], dict[str, float]]:
    """Fetch /me and /me/top/artists across all three time ranges.

    Returns:
        (me_profile, deduplicated_artists, {artist_id: recency_weight})

    Artists that appear in multiple time ranges keep the data from the most
    recent range (setdefault preserves first insertion = short_term first).
    The weight dict records the highest (most recent) weight per artist.
    """
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(headers=headers, timeout=15) as client:
        me = (await client.get(f"{SPOTIFY_API}/me")).raise_for_status().json()

        seen: dict[str, dict] = {}
        artist_weights: dict[str, float] = {}
        for time_range in TIME_RANGES:
            weight = TIME_RANGE_WEIGHTS[time_range]
            resp = await client.get(
                f"{SPOTIFY_API}/me/top/artists",
                params={"time_range": time_range, "limit": 50},
            )
            resp.raise_for_status()
            for artist in resp.json().get("items", []):
                aid = artist["id"]
                seen.setdefault(aid, artist)           # keep most-recent data
                artist_weights.setdefault(aid, weight) # keep highest weight

    return me, list(seen.values()), artist_weights


def _sync_artists(token: str, spotify_artists: list[dict]) -> dict[str, Artist]:
    """
    Upsert the user's top artists into DB. For each artist:
      - Create record if missing, fetching audio features + related genres.
      - Always recompute the embedding so algorithm changes (weight tuning,
        genre selection) take effect on the next sync without a manual DB wipe.
    Runs in a thread — uses sync httpx + SQLite.
    """
    enricher = SpotifyEnricher(token)
    try:
        with get_session() as session:
            result: dict[str, Artist] = {}

            for sa in spotify_artists:
                sid = sa["id"]
                artist = session.get(Artist, sid)

                if artist is None:
                    # New artist: fetch audio features and widen genre signal
                    # with related artists' genres.
                    audio_feat: dict | None = None
                    try:
                        audio_feat = enricher.get_audio_features(sid)
                    except Exception:
                        log.warning("Could not fetch audio features for %s", sid)

                    base_genres: list[str] = sa.get("genres", [])
                    related_genres = enricher.get_related_genres(sid)
                    merged_genres = list(dict.fromkeys(base_genres + related_genres))

                    artist = Artist(
                        id=sid,
                        name=sa["name"],
                        spotify_id=sid,
                        genres=json.dumps(merged_genres),
                        popularity=sa.get("popularity"),
                        audio_features=json.dumps(audio_feat) if audio_feat else None,
                        last_enriched=datetime.utcnow(),
                    )
                    session.add(artist)

                # Always recompute embedding for the user's own top artists so
                # that tuning changes (_TEXT_WEIGHT, _select_genres, etc.) apply
                # immediately on the next sync without a manual DB migration.
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
        obj.taste_modes = json.dumps(taste_mode_map, cls=_NumpyEncoder)
        obj.last_synced = datetime.utcnow()
        session.add(obj)
        session.commit()


@router.post("/sync", response_model=UserProfile)
async def sync_user(authorization: str = Header(...)) -> UserProfile:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization.removeprefix("Bearer ")

    try:
        user, spotify_artists, artist_weights = await _fetch_spotify_data(token)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail="Spotify API error",
        ) from exc

    spotify_id = user["id"]
    display_name = user.get("display_name")
    top_ids = [sa["id"] for sa in spotify_artists]

    artist_map = await asyncio.to_thread(_sync_artists, token, spotify_artists)

    embeddings: dict[str, np.ndarray] = {
        aid: np.frombuffer(a.embedding, dtype=np.float32).copy()
        for aid, a in artist_map.items()
        if a.embedding is not None
    }
    taste_mode_map: dict = {}
    if embeddings:
        taste_mode_map = await asyncio.to_thread(
            compute_taste_modes, embeddings, top_ids, artist_weights
        )

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
