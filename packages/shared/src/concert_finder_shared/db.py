from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import sqlite_vec
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

_raw = os.getenv("DATABASE_URL", "")
# Resolve relative to repo root when DATABASE_URL is unset.
# This file sits at packages/shared/src/concert_finder_shared/db.py,
# so parents[4] = repo root.
DB_PATH = (
    Path(_raw).expanduser()
    if _raw
    else Path(__file__).resolve().parents[4] / "data" / "concert.db"
)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _load_sqlite_vec(dbapi_conn, _):
    dbapi_conn.enable_load_extension(True)
    sqlite_vec.load(dbapi_conn)
    dbapi_conn.enable_load_extension(False)


def init_db() -> None:
    """Create all SQLModel tables. Idempotent — safe to call on every startup."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    from concert_finder_shared import models as _models  # noqa: F401 — registers metadata
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
