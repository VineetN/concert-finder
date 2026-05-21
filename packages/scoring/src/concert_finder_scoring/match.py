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

    Final score = max cosine_similarity(artist_vec, mode_centroid) × billing_weight,
    taken over all (artist, mode) pairs on the bill.
    """
    best_sim = 0.0
    best_artist = ""
    best_mode_label = ""
    best_mode_dominant = False

    for ea, artist in bill:
        if artist.embedding is None:
            continue
        artist_vec = np.frombuffer(artist.embedding, dtype=np.float32)
        weight = BILLING_WEIGHTS.get(ea.billing_position, _DEFAULT_WEIGHT)

        for mode in taste_modes.values():
            centroid = np.array(mode["centroid"], dtype=np.float32)
            denom = np.linalg.norm(artist_vec) * np.linalg.norm(centroid) + 1e-8
            sim = float(np.dot(artist_vec, centroid) / denom) * weight

            if sim > best_sim:
                best_sim = sim
                best_artist = artist.name
                best_mode_label = mode.get("label", "?")
                best_mode_dominant = mode.get("is_dominant", False)

    return MatchResult(
        event_id=event.id,
        score=round(best_sim, 4),
        category=_classify(best_sim, best_mode_dominant),
        driver_artist=best_artist,
        driver_mode=best_mode_label,
    )


def _classify(sim: float, dominant_mode: bool) -> EventCategory:
    if dominant_mode and sim > 0.75:
        return EventCategory.SAFE_BET
    if not dominant_mode and sim > 0.60:
        return EventCategory.STRETCH_PICK
    return EventCategory.REGULAR
