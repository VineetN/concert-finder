from __future__ import annotations

import json
import logging

import httpx

from concert_finder_shared.models import Artist

log = logging.getLogger(__name__)

SPOTIFY_API = "https://api.spotify.com/v1"
AUDIO_FEATURE_KEYS = [
    "danceability", "energy", "valence",
    "acousticness", "instrumentalness", "speechiness", "tempo",
]


class SpotifyEnricher:
    def __init__(self, access_token: str) -> None:
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )

    def enrich_artist(self, name: str) -> Artist | None:
        """Search Spotify for an artist by name and return an Artist record.

        Genres and audio features are best-effort: Spotify's API restricts
        these endpoints for client_credentials apps (post Nov 2024), so they
        may come back empty. The Artist record is still created with a Spotify
        ID so it can be de-duplicated on future runs.
        """
        result = self._search_artist(name)
        if not result:
            log.debug("No Spotify match for %r", name)
            return None

        spotify_id, canonical_name, genres, popularity = result

        audio_features = None
        try:
            audio_features = self._fetch_audio_features(spotify_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (403, 404):
                raise
            log.debug("audio features unavailable for %r (%s)", name, exc.response.status_code)

        return Artist(
            id=spotify_id,
            name=canonical_name,
            spotify_id=spotify_id,
            genres=json.dumps(genres),
            popularity=popularity,
            audio_features=json.dumps(audio_features) if audio_features else None,
        )

    def get_audio_features(self, spotify_id: str) -> dict | None:
        """Fetch averaged audio features for an artist we already have the ID for."""
        try:
            return self._fetch_audio_features(spotify_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (403, 404):
                raise
            log.debug("audio features unavailable for %s (%s)", spotify_id, exc.response.status_code)
            return None

    def _search_artist(self, name: str) -> tuple[str, str, list, int | None] | None:
        """Search for artist by name. Returns (id, canonical_name, genres, popularity) or None."""
        r = self._client.get(
            f"{SPOTIFY_API}/search",
            params={"q": name, "type": "artist", "limit": 1},
        )
        r.raise_for_status()
        items = r.json().get("artists", {}).get("items", [])
        if not items:
            return None
        a = items[0]
        return (
            a["id"],
            a["name"],
            a.get("genres", []),
            a.get("popularity"),
        )

    def _fetch_audio_features(self, spotify_id: str) -> dict | None:
        """Fetch top tracks then average their audio features. May raise 403."""
        r = self._client.get(
            f"{SPOTIFY_API}/artists/{spotify_id}/top-tracks",
            params={"market": "US"},
        )
        r.raise_for_status()
        track_ids = [t["id"] for t in r.json().get("tracks", [])[:10]]
        if not track_ids:
            return None

        r2 = self._client.get(
            f"{SPOTIFY_API}/audio-features",
            params={"ids": ",".join(track_ids)},
        )
        r2.raise_for_status()
        features = [f for f in r2.json().get("audio_features", []) if f]
        if not features:
            return None

        avg = {k: sum(f[k] for f in features if k in f) / len(features) for k in AUDIO_FEATURE_KEYS}
        avg["tempo_norm"] = max(0.0, min(1.0, (avg.pop("tempo") - 40) / 180))
        return avg

    def close(self) -> None:
        self._client.close()
