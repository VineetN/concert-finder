"""Tests for concert_finder_scoring.match — pure scoring logic, no I/O."""
from __future__ import annotations

import struct
from unittest.mock import MagicMock

import numpy as np
import pytest

from concert_finder_scoring.match import (
    EventCategory,
    MatchResult,
    _classify,
    score_event,
)


# ── _classify ────────────────────────────────────────────────────────────────

class TestClassify:
    def test_safe_bet_above_threshold(self):
        assert _classify(0.74, dominant_mode=True) == EventCategory.SAFE_BET

    def test_safe_bet_at_boundary(self):
        # Strictly above 0.73 → safe bet
        assert _classify(0.731, dominant_mode=True) == EventCategory.SAFE_BET

    def test_safe_bet_exactly_at_threshold_is_regular(self):
        # 0.73 is NOT above 0.73 — boundary is exclusive
        assert _classify(0.73, dominant_mode=True) == EventCategory.REGULAR

    def test_stretch_pick_non_dominant(self):
        assert _classify(0.71, dominant_mode=False) == EventCategory.STRETCH_PICK

    def test_stretch_pick_at_boundary_is_regular(self):
        assert _classify(0.70, dominant_mode=False) == EventCategory.REGULAR

    def test_dominant_high_sim_is_safe_bet_not_stretch(self):
        # dominant mode + high score → SAFE_BET, not STRETCH_PICK
        assert _classify(0.80, dominant_mode=True) == EventCategory.SAFE_BET

    def test_non_dominant_high_sim_is_stretch(self):
        assert _classify(0.80, dominant_mode=False) == EventCategory.STRETCH_PICK

    def test_low_score_is_regular(self):
        assert _classify(0.50, dominant_mode=True) == EventCategory.REGULAR
        assert _classify(0.50, dominant_mode=False) == EventCategory.REGULAR

    def test_zero_score_is_regular(self):
        assert _classify(0.0, dominant_mode=True) == EventCategory.REGULAR


# ── score_event ──────────────────────────────────────────────────────────────

def _make_vec(values: list[float]) -> bytes:
    """Pack a float32 numpy array into bytes (as stored in artist.embedding)."""
    arr = np.array(values, dtype=np.float32)
    return arr.tobytes()


def _make_artist(name: str, embedding: bytes | None):
    a = MagicMock()
    a.name = name
    a.embedding = embedding
    return a


def _make_ea(billing_position: int):
    ea = MagicMock()
    ea.billing_position = billing_position
    return ea


def _make_event(event_id: str = "evt-1"):
    e = MagicMock()
    e.id = event_id
    return e


def _taste_modes(centroid: list[float], *, dominant: bool = True) -> dict:
    return {
        "0": {
            "centroid": centroid,
            "label": "indie",
            "is_dominant": dominant,
        }
    }


class TestScoreEvent:
    def test_returns_match_result(self):
        vec = [1.0, 0.0, 0.0]
        bill = [(_make_ea(0), _make_artist("Headliner", _make_vec(vec)))]
        result = score_event(_make_event(), bill, _taste_modes(vec, dominant=True))
        assert isinstance(result, MatchResult)

    def test_perfect_match_headliner(self):
        vec = [1.0, 0.0, 0.0]
        bill = [(_make_ea(0), _make_artist("Band A", _make_vec(vec)))]
        modes = _taste_modes(vec, dominant=True)
        result = score_event(_make_event(), bill, modes)
        # headliner billing weight = 1.0 × cosine_sim 1.0 = 1.0
        assert result.score == pytest.approx(1.0, abs=1e-3)
        assert result.category == EventCategory.SAFE_BET
        assert result.driver_artist == "Band A"

    def test_billing_weight_reduces_opener_score(self):
        vec = [1.0, 0.0, 0.0]
        # Same perfect vector but opener (billing_position=2, weight=0.5)
        bill = [(_make_ea(2), _make_artist("Opener", _make_vec(vec)))]
        modes = _taste_modes(vec, dominant=True)
        result = score_event(_make_event(), bill, modes)
        assert result.score == pytest.approx(0.5, abs=1e-3)

    def test_support_billing_weight(self):
        vec = [1.0, 0.0, 0.0]
        bill = [(_make_ea(1), _make_artist("Support", _make_vec(vec)))]
        modes = _taste_modes(vec, dominant=True)
        result = score_event(_make_event(), bill, modes)
        assert result.score == pytest.approx(0.7, abs=1e-3)

    def test_best_artist_drives_score(self):
        """Headliner is a bad match, opener is a great match — opener wins."""
        good_vec = [1.0, 0.0, 0.0]
        bad_vec  = [0.0, 1.0, 0.0]
        centroid = [1.0, 0.0, 0.0]
        bill = [
            (_make_ea(0), _make_artist("Headliner", _make_vec(bad_vec))),
            (_make_ea(2), _make_artist("Opener",    _make_vec(good_vec))),
        ]
        modes = _taste_modes(centroid, dominant=True)
        result = score_event(_make_event(), bill, modes)
        # headliner: sim≈0 × 1.0 = 0; opener: sim=1.0 × 0.5 = 0.5
        assert result.driver_artist == "Opener"
        assert result.score == pytest.approx(0.5, abs=1e-3)

    def test_artist_without_embedding_skipped(self):
        bill = [(_make_ea(0), _make_artist("Ghost", None))]
        modes = _taste_modes([1.0, 0.0, 0.0])
        result = score_event(_make_event(), bill, modes)
        assert result.score == 0.0
        assert result.category == EventCategory.REGULAR

    def test_empty_bill(self):
        result = score_event(_make_event(), [], _taste_modes([1.0, 0.0, 0.0]))
        assert result.score == 0.0

    def test_non_dominant_mode_gives_stretch_pick(self):
        vec = [1.0, 0.0, 0.0]
        bill = [(_make_ea(0), _make_artist("Artist", _make_vec(vec)))]
        modes = _taste_modes(vec, dominant=False)
        result = score_event(_make_event(), bill, modes)
        assert result.category == EventCategory.STRETCH_PICK

    def test_event_id_propagated(self):
        vec = [1.0, 0.0, 0.0]
        bill = [(_make_ea(0), _make_artist("X", _make_vec(vec)))]
        result = score_event(_make_event("my-event-id"), bill, _taste_modes(vec))
        assert result.event_id == "my-event-id"

    def test_stretch_pick_fires_independently_of_dominant_score(self):
        """Non-dominant mode fires Stretch Pick even when dominant also scores (but < 0.73)."""
        dom_vec = [1.0, 0.0, 0.0]
        sec_vec = [0.0, 1.0, 0.0]
        artist_vec = [0.6, 0.8, 0.0]  # closer to sec_vec; dom sim≈0.6, sec sim≈0.8
        bill = [(_make_ea(0), _make_artist("Artist", _make_vec(artist_vec)))]
        modes = {
            "0": {"centroid": dom_vec, "label": "dominant", "is_dominant": True},
            "1": {"centroid": sec_vec, "label": "secondary", "is_dominant": False},
        }
        result = score_event(_make_event(), bill, modes)
        # Dominant score ≈ 0.60 (below 0.73 Safe Bet), secondary ≈ 0.80 (above 0.70)
        assert result.category == EventCategory.STRETCH_PICK
        assert result.driver_mode == "secondary"

    def test_safe_bet_takes_priority_over_stretch(self):
        """Safe Bet wins even when a non-dominant mode also scores above 0.70."""
        dom_vec = [1.0, 0.0, 0.0]
        sec_vec = [0.0, 1.0, 0.0]
        artist_vec = [0.8, 0.6, 0.0]  # dom sim≈0.8 (Safe Bet), sec sim≈0.6
        bill = [(_make_ea(0), _make_artist("Artist", _make_vec(artist_vec)))]
        modes = {
            "0": {"centroid": dom_vec, "label": "dominant", "is_dominant": True},
            "1": {"centroid": sec_vec, "label": "secondary", "is_dominant": False},
        }
        result = score_event(_make_event(), bill, modes)
        assert result.category == EventCategory.SAFE_BET
        assert result.driver_mode == "dominant"

    def test_score_rounded_to_4_decimal_places(self):
        # Use orthogonal vectors to get a deterministic non-trivial sim
        v1 = [0.6, 0.8, 0.0]
        v2 = [0.8, 0.6, 0.0]
        bill = [(_make_ea(0), _make_artist("A", _make_vec(v1)))]
        modes = _taste_modes(v2)
        result = score_event(_make_event(), bill, modes)
        assert result.score == round(result.score, 4)
