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
        spotify_id = self._search_artist(name)
        if not spotify_id:
            log.debug("No Spotify match for %r", name)
            return None

        artist_data = self._get_artist(spotify_id)
        top_tracks = self._get_top_tracks(spotify_id)
        audio_features = self._avg_audio_features([t["id"] for t in top_tracks[:10]])

        return Artist(
            id=spotify_id,
            name=artist_data["name"],
            spotify_id=spotify_id,
            genres=json.dumps(artist_data.get("genres", [])),
            popularity=artist_data.get("popularity"),
            audio_features=json.dumps(audio_features) if audio_features else None,
        )

    def _search_artist(self, name: str) -> str | None:
        r = self._client.get(f"{SPOTIFY_API}/search", params={"q": name, "type": "artist", "limit": 1})
        r.raise_for_status()
        items = r.json().get("artists", {}).get("items", [])
        return items[0]["id"] if items else None

    def _get_artist(self, spotify_id: str) -> dict:
        r = self._client.get(f"{SPOTIFY_API}/artists/{spotify_id}")
        r.raise_for_status()
        return r.json()

    def _get_top_tracks(self, spotify_id: str) -> list[dict]:
        r = self._client.get(
            f"{SPOTIFY_API}/artists/{spotify_id}/top-tracks",
            params={"market": "US"},
        )
        r.raise_for_status()
        return r.json().get("tracks", [])

    def _avg_audio_features(self, track_ids: list[str]) -> dict | None:
        if not track_ids:
            return None
        r = self._client.get(f"{SPOTIFY_API}/audio-features", params={"ids": ",".join(track_ids)})
        r.raise_for_status()
        features = [f for f in r.json().get("audio_features", []) if f]
        if not features:
            return None

        avg = {k: sum(f[k] for f in features if k in f) / len(features) for k in AUDIO_FEATURE_KEYS}
        # Normalize tempo from ~[40, 220] BPM to [0, 1]
        avg["tempo_norm"] = max(0.0, min(1.0, (avg.pop("tempo") - 40) / 180))
        return avg

    def get_audio_features(self, spotify_id: str) -> dict | None:
        """Fetch + average audio features for an artist we already know the ID for."""
        top_tracks = self._get_top_tracks(spotify_id)
        return self._avg_audio_features([t["id"] for t in top_tracks[:10]])

    def close(self) -> None:
        self._client.close()
