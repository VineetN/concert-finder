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


app = FastAPI(title="Concert Finder API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .routers import events, user  # noqa: E402 — after app is defined

app.include_router(events.router, prefix="/events", tags=["events"])
app.include_router(user.router, prefix="/user", tags=["user"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
