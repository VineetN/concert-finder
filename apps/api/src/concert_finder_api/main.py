from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from concert_finder_api.db import init_db
    from concert_finder_scoring.embeddings import _get_model
    init_db()
    _get_model()  # pre-warm so first scoring request isn't slow
    yield


app = FastAPI(title="Concert Finder API", version="0.1.0", lifespan=lifespan, redirect_slashes=False)

_frontend = os.getenv("FRONTEND_URL", "http://localhost:3000")
# Accept both localhost and 127.0.0.1 variants so dev works from either origin
_origins = list(dict.fromkeys([
    _frontend,
    _frontend.replace("localhost", "127.0.0.1") if "localhost" in _frontend else _frontend,
    _frontend.replace("127.0.0.1", "localhost") if "127.0.0.1" in _frontend else _frontend,
]))
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .routers import events, user  # noqa: E402 — after app is defined

app.include_router(events.router, tags=["events"])
app.include_router(user.router, prefix="/user", tags=["user"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
