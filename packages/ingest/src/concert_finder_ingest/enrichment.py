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

        # Widen genre signal with related artists' genres. Related artists are
        # sonically adjacent by Spotify's own model, so their genre tags carry
        # meaningful signal for embedding even when the primary artist's own
        # tag list is sparse (e.g. many experimental/niche artists have only
        # "experimental" as their sole genre).
        related_genres = self.get_related_genres(spotify_id)
        merged_genres = list(dict.fromkeys(genres + related_genres))  # primary first, deduped

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
            genres=json.dumps(merged_genres),
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

    def get_related_genres(self, spotify_id: str) -> list[str]:
        """
        Fetch genres from up to 5 related artists to widen the genre signal.

        Spotify's related-artists endpoint returns artists that are sonically
        and contextually adjacent. Their genre tags often include more specific
        labels than the primary artist's own tags, improving embedding quality
        for niche or experimental artists.

        Returns a deduplicated list of genres (not including the primary artist's
        own genres — merge at the call site). Returns [] on any API error.
        """
        try:
            r = self._client.get(f"{SPOTIFY_API}/artists/{spotify_id}/related-artists")
            r.raise_for_status()
            related = r.json().get("artists", [])[:5]
            genres: list[str] = []
            seen: set[str] = set()
            for a in related:
                for g in a.get("genres", []):
                    if g not in seen:
                        genres.append(g)
                        seen.add(g)
            return genres
        except Exception:
            log.debug("Could not fetch related artists for %s", spotify_id)
            return []

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
