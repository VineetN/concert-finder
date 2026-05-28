from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from concert_finder_shared.models import Artist, Event, EventArtist

# Weight per billing slot: headliner, direct support, opener+
BILLING_WEIGHTS: dict[int, float] = {0: 1.0, 1: 0.7}
_DEFAULT_WEIGHT = 0.5


class EventCategory(str, Enum):
    SAFE_BET = "safe_bet"
    STRETCH_PICK = "stretch_pick"
    REGULAR = "regular"


@dataclass
class MatchResult:
    event_id: str
    score: float
    category: EventCategory
    driver_artist: str   # name of the artist that drove the match
    driver_mode: str     # label of the taste mode it matched


def score_event(
    event: Event,
    bill: list[tuple[EventArtist, Artist]],
    taste_modes: dict,  # {mode_id: {centroid, label, is_dominant, ...}}
) -> MatchResult:
    """
    Score an event against all of a user's taste modes.

    Dominant and non-dominant modes are tracked separately so that a strong
    match to a secondary taste mode can surface as a Stretch Pick even when
    the dominant mode also scores decently (but below the Safe Bet threshold).
    """
    best_dom_sim = 0.0
    best_dom_artist = ""
    best_dom_label = ""

    best_sec_sim = 0.0
    best_sec_artist = ""
    best_sec_label = ""

    for ea, artist in bill:
        if artist.embedding is None:
            continue
        artist_vec = np.frombuffer(artist.embedding, dtype=np.float32)
        weight = BILLING_WEIGHTS.get(ea.billing_position, _DEFAULT_WEIGHT)

        for mode in taste_modes.values():
            centroid = np.array(mode["centroid"], dtype=np.float32)
            denom = np.linalg.norm(artist_vec) * np.linalg.norm(centroid) + 1e-8
            sim = float(np.dot(artist_vec, centroid) / denom) * weight

            if mode.get("is_dominant", False):
                if sim > best_dom_sim:
                    best_dom_sim = sim
                    best_dom_artist = artist.name
                    best_dom_label = mode.get("label", "?")
            else:
                if sim > best_sec_sim:
                    best_sec_sim = sim
                    best_sec_artist = artist.name
                    best_sec_label = mode.get("label", "?")

    # Safe Bet takes priority; Stretch Pick fires independently of dominant score
    if best_dom_sim > 0.73:
        return MatchResult(
            event_id=event.id,
            score=round(best_dom_sim, 4),
            category=EventCategory.SAFE_BET,
            driver_artist=best_dom_artist,
            driver_mode=best_dom_label,
        )
    if best_sec_sim > 0.70:
        return MatchResult(
            event_id=event.id,
            score=round(best_sec_sim, 4),
            category=EventCategory.STRETCH_PICK,
            driver_artist=best_sec_artist,
            driver_mode=best_sec_label,
        )
    # Regular — report whichever mode scored higher
    if best_dom_sim >= best_sec_sim:
        return MatchResult(
            event_id=event.id,
            score=round(best_dom_sim, 4),
            category=EventCategory.REGULAR,
            driver_artist=best_dom_artist,
            driver_mode=best_dom_label,
        )
    return MatchResult(
        event_id=event.id,
        score=round(best_sec_sim, 4),
        category=EventCategory.REGULAR,
        driver_artist=best_sec_artist,
        driver_mode=best_sec_label,
    )


def _classify(sim: float, dominant_mode: bool) -> EventCategory:
    # Thresholds calibrated for genre-embedding space (Last.fm tags).
    # Text-only embeddings compressed scores into a wider range; with real
    # genre signal scores cluster in 0.65-0.84, so both bounds shift up.
    if dominant_mode and sim > 0.73:
        return EventCategory.SAFE_BET
    if not dominant_mode and sim > 0.70:
        return EventCategory.STRETCH_PICK
    return EventCategory.REGULAR
