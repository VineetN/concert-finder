from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Artist(SQLModel, table=True):
    # spotify_id when available; else slugified name (e.g. "the-crocodiles")
    id: str = Field(primary_key=True)
    name: str
    spotify_id: Optional[str] = None
    genres: str = "[]"             # JSON-serialized list[str]
    popularity: Optional[int] = None
    audio_features: Optional[str] = None   # JSON dict — 7 Spotify features + tempo_norm
    embedding: Optional[bytes] = None      # serialized float32 numpy vector
    last_enriched: Optional[datetime] = None

    @property
    def genres_list(self) -> list[str]:
        return json.loads(self.genres)

    @property
    def audio_features_dict(self) -> dict | None:
        return json.loads(self.audio_features) if self.audio_features else None


class Event(SQLModel, table=True):
    # Stable ID: sha1(date + venue + headliner) — deduplicates across scrapers
    id: str = Field(primary_key=True)
    date: datetime
    venue: str
    ticket_url: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    source: str   # "songkick" | "neumos" | "crocodile" | etc.
    scraped_at: datetime = Field(default_factory=datetime.utcnow)


class EventArtist(SQLModel, table=True):
    event_id: str = Field(foreign_key="event.id", primary_key=True)
    artist_id: str = Field(foreign_key="artist.id", primary_key=True)
    billing_position: int = 0   # 0 = headliner, 1 = direct support, 2+ = opener


class UserSession(SQLModel, table=True):
    """Ephemeral per-login — rebuilt on every Spotify OAuth flow."""
    id: str = Field(primary_key=True)   # Spotify user ID
    display_name: Optional[str] = None
    top_artist_ids: str = "[]"          # JSON list[str] of Spotify artist IDs
    # JSON: {cluster_id: {centroid: list[float], label: str, is_dominant: bool, artist_ids: list[str]}}
    taste_modes: Optional[str] = None
    last_synced: datetime = Field(default_factory=datetime.utcnow)
