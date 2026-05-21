from __future__ import annotations

import logging
from functools import lru_cache

import numpy as np

log = logging.getLogger(__name__)

# bge-small outperforms MiniLM on semantic similarity at similar size (130MB vs 80MB)
MODEL_ID = "BAAI/bge-small-en-v1.5"

# 50/50 gives audio features enough influence to separate sonically similar
# artists that share genre labels (e.g. Burial vs Four Tet — both "electronic").
# Raise _AUDIO_WEIGHT toward 0.7 if genre-tag quality is poor; lower it if
# Spotify audio features are missing for many artists in your library.
_TEXT_WEIGHT = 0.5
_AUDIO_WEIGHT = 0.5


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer
    log.info("Loading embedding model %s (first load only)...", MODEL_ID)
    return SentenceTransformer(MODEL_ID)


def embed_texts(texts: list[str]) -> np.ndarray:
    """Encode a list of strings → normalized float32 matrix of shape (n, dim)."""
    return _get_model().encode(texts, normalize_embeddings=True, show_progress_bar=False)


def _select_genres(genres: list[str], n: int = 3) -> list[str]:
    """
    Pick the n most specific genres by preferring longer strings.

    Longer genre labels tend to be more specific:
        "icelandic post-rock"  >  "post-rock"  >  "rock"
        "lowercase"            >  "experimental"

    This prevents broad shared tags like "electronic" or "rock" from
    dominating the embedding when more precise labels are available,
    which otherwise collapses sonically distinct artists into one cluster.
    """
    return sorted(genres, key=len, reverse=True)[:n]


def build_artist_vector(
    name: str,
    genres: list[str],
    audio_features: dict | None = None,
) -> np.ndarray:
    """
    Build a 391-dim artist vector: 384-dim text (50%) + 7-dim audio (50%).

    Genre selection: uses the 3 most specific genres (longest strings).
    Audio features: zero-padded when unavailable so all vectors share the
    same dimensionality (384 + 7 = 391).
    """
    specific = _select_genres(genres)
    genre_str = ", ".join(specific) if specific else "unknown genre"
    text_vec = embed_texts([f"{name} — {genre_str}"])[0]

    keys = ["danceability", "energy", "valence", "acousticness",
            "instrumentalness", "speechiness", "tempo_norm"]
    if audio_features:
        audio_vec = np.array([audio_features.get(k, 0.0) for k in keys], dtype=np.float32)
        norm = np.linalg.norm(audio_vec)
        if norm > 0:
            audio_vec /= norm
    else:
        # Zero-pad: keeps dimensionality consistent; cosine sim still works
        audio_vec = np.zeros(len(keys), dtype=np.float32)

    combined = np.concatenate([text_vec * _TEXT_WEIGHT, audio_vec * _AUDIO_WEIGHT])
    return combined / (np.linalg.norm(combined) + 1e-8)
