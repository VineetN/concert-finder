"""Tests for the /events API endpoint using FastAPI TestClient with mocked deps."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient


def _make_embedding(dim: int = 384) -> bytes:
    rng = np.random.default_rng(42)
    vec = rng.random(dim).astype(np.float32)
    vec /= np.linalg.norm(vec)
    return vec.tobytes()


def _taste_modes_json(dominant: bool = True) -> str:
    rng = np.random.default_rng(0)
    centroid = rng.random(384).astype(np.float32)
    centroid /= np.linalg.norm(centroid)
    return json.dumps({
        "0": {
            "centroid": centroid.tolist(),
            "label": "indie",
            "is_dominant": dominant,
        }
    })


@pytest.fixture()
def client():
    from concert_finder_api.main import app
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def mock_spotify_id():
    """Patch _resolve_spotify_id so tests don't need a real Spotify token."""
    with patch(
        "concert_finder_api.routers.events._resolve_spotify_id",
        return_value="test_user",
    ) as m:
        yield m


@pytest.fixture()
def mock_load_and_score_empty():
    """Simulate a synced user with no upcoming events."""
    with patch(
        "concert_finder_api.routers.events._load_and_score",
        return_value=(json.loads(_taste_modes_json()), []),
    ):
        yield


@pytest.fixture()
def mock_load_and_score_with_events():
    """Simulate one scored event returned by the scoring layer."""
    from concert_finder_scoring.match import EventCategory, MatchResult

    event = MagicMock()
    event.id = "evt-1"
    event.date = datetime.now() + timedelta(days=7)
    event.venue = "Neumos"
    event.ticket_url = "https://example.com/tickets"
    event.price_min = None
    event.price_max = None

    artist = MagicMock()
    artist.name = "Test Band"

    ea = MagicMock()
    ea.billing_position = 0

    match = MatchResult(
        event_id="evt-1",
        score=0.80,
        category=EventCategory.SAFE_BET,
        driver_artist="Test Band",
        driver_mode="indie",
    )

    taste_modes = json.loads(_taste_modes_json())
    with patch(
        "concert_finder_api.routers.events._load_and_score",
        return_value=(taste_modes, [(event, [(ea, artist)], match)]),
    ):
        yield


# ── /events ───────────────────────────────────────────────────────────────────

class TestListEvents:
    def test_401_without_authorization_header(self, client):
        resp = client.get("/events")
        assert resp.status_code == 422  # missing required header → validation error

    def test_invalid_token_returns_401(self, client):
        with patch(
            "concert_finder_api.routers.events._resolve_spotify_id",
            side_effect=__import__("httpx").HTTPStatusError(
                "401", request=MagicMock(), response=MagicMock(status_code=401)
            ),
        ):
            resp = client.get("/events", headers={"Authorization": "Bearer bad"})
        assert resp.status_code == 401
        assert "Spotify token invalid" in resp.json()["detail"]

    def test_unsynced_user_returns_404(self, client, mock_spotify_id):
        with patch(
            "concert_finder_api.routers.events._load_and_score",
            return_value=({}, []),
        ):
            resp = client.get("/events", headers={"Authorization": "Bearer tok"})
        assert resp.status_code == 404
        assert "not synced" in resp.json()["detail"]

    def test_empty_events_returns_empty_list(
        self, client, mock_spotify_id, mock_load_and_score_empty
    ):
        resp = client.get("/events", headers={"Authorization": "Bearer tok"})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_scored_event_shape(
        self, client, mock_spotify_id, mock_load_and_score_with_events
    ):
        resp = client.get("/events", headers={"Authorization": "Bearer tok"})
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 1
        ev = events[0]
        assert ev["id"] == "evt-1"
        assert ev["venue"] == "Neumos"
        assert ev["score"] == pytest.approx(0.80)
        assert ev["category"] == "safe_bet"
        assert ev["driver_artist"] == "Test Band"
        assert ev["driver_mode"] == "indie"
        assert ev["ticket_url"] == "https://example.com/tickets"
        assert isinstance(ev["artists"], list)

    def test_category_filter_forwarded(self, client, mock_spotify_id):
        with patch(
            "concert_finder_api.routers.events._load_and_score",
            return_value=(json.loads(_taste_modes_json()), []),
        ) as mock_fn:
            client.get(
                "/events?category=safe_bet",
                headers={"Authorization": "Bearer tok"},
            )
            _, call_kwargs = mock_fn.call_args
            # category_filter arg should be "safe_bet"
            assert "safe_bet" in mock_fn.call_args.args

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
