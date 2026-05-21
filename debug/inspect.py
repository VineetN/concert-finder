#!/usr/bin/env python3
"""
Debug inspection tool — dumps taste mode clusters and scored events to files.

Usage:
    uv run python debug/inspect.py <spotify_user_id>

    spotify_user_id is your Spotify ID (visible in the /user/sync response,
    or at open.spotify.com/account — it's the string under your display name).

Output (written to debug/output/):
    clusters.json       — each taste mode with its artists, sorted by cluster
    safe_bets.csv       — top Safe Bet events (score desc)
    stretch_picks.csv   — top Stretch Pick events (score desc)
    all_events.csv      — every scored event, all categories

Requires the DB to be populated (run `just scrape` and log in via the frontend first).
Does NOT require the API server to be running.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# Resolve repo root so imports work regardless of where the script is invoked from
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages" / "shared" / "src"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "scoring" / "src"))

import numpy as np
from sqlmodel import select

from concert_finder_shared.db import get_session, init_db
from concert_finder_shared.models import Artist, Event, EventArtist, UserSession
from concert_finder_scoring.match import EventCategory, score_event

OUTPUT_DIR = Path(__file__).parent / "output"
LOOKAHEAD_DAYS = 60


# ── helpers ───────────────────────────────────────────────────────────────────

def load_user(session, spotify_user_id: str) -> UserSession:
    user = session.get(UserSession, spotify_user_id)
    if user is None:
        print(f"  No UserSession found for '{spotify_user_id}'.")
        print("  → Log in via the frontend (or POST /user/sync) first.")
        sys.exit(1)
    if not user.taste_modes:
        print("  UserSession exists but taste_modes is empty.")
        print("  → Call POST /user/sync to re-cluster.")
        sys.exit(1)
    return user


def load_upcoming_events(session) -> tuple[list[Event], dict[str, list]]:
    now = datetime.utcnow()
    cutoff = now + timedelta(days=LOOKAHEAD_DAYS)
    events = session.exec(
        select(Event)
        .where(Event.date >= now, Event.date <= cutoff)
        .order_by(Event.date)
    ).all()

    if not events:
        return [], {}

    event_ids = [e.id for e in events]
    bill_rows = session.exec(
        select(EventArtist, Artist)
        .join(Artist, Artist.id == EventArtist.artist_id)
        .where(EventArtist.event_id.in_(event_ids))
        .order_by(EventArtist.billing_position)
    ).all()

    bills: dict[str, list] = defaultdict(list)
    for ea, artist in bill_rows:
        bills[ea.event_id].append((ea, artist))

    return events, bills


# ── cluster dump ──────────────────────────────────────────────────────────────

def dump_clusters(taste_modes: dict, artist_map: dict[str, Artist]) -> None:
    output = []
    for mode_id, mode in sorted(taste_modes.items()):
        artist_names = []
        for aid in mode.get("artist_ids", []):
            a = artist_map.get(aid)
            artist_names.append(a.name if a else aid)

        output.append({
            "mode_id": mode_id,
            "label": mode.get("label", mode_id),
            "is_dominant": mode.get("is_dominant", False),
            "artist_count": len(artist_names),
            "artists": artist_names,
        })

    out_path = OUTPUT_DIR / "clusters.json"
    out_path.write_text(json.dumps(output, indent=2))

    print(f"\n{'─'*60}")
    print("TASTE MODE CLUSTERS")
    print(f"{'─'*60}")
    for m in output:
        dominant_tag = "  ★ dominant" if m["is_dominant"] else ""
        print(f"\n  Mode {m['mode_id']}{dominant_tag}")
        for name in m["artists"]:
            print(f"    · {name}")

    print(f"\n  → Full JSON written to {out_path.relative_to(REPO_ROOT)}")


# ── event scoring + CSV dump ──────────────────────────────────────────────────

def dump_events(events: list[Event], bills: dict, taste_modes: dict) -> None:
    rows = []
    for event in events:
        bill = bills.get(event.id, [])
        if not bill:
            continue

        match = score_event(event, bill, taste_modes)
        bill_str = " / ".join(
            f"{artist.name}{'*' if artist.name == match.driver_artist else ''}"
            for _, artist in sorted(bill, key=lambda x: x[0].billing_position)
        )
        rows.append({
            "date": event.date.strftime("%a %b %-d"),
            "venue": event.venue,
            "bill": bill_str,
            "score": f"{match.score:.3f}",
            "category": match.category.value,
            "driver_artist": match.driver_artist,
            "driver_mode": match.driver_mode,
            "ticket_url": event.ticket_url or "",
            "price": (
                f"${event.price_min:.0f}"
                if event.price_min is not None else ""
            ),
        })

    rows.sort(key=lambda r: float(r["score"]), reverse=True)

    fieldnames = ["date", "venue", "bill", "score", "category",
                  "driver_artist", "driver_mode", "price", "ticket_url"]

    def write_csv(path: Path, data: list[dict]) -> None:
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

    safe_bets    = [r for r in rows if r["category"] == EventCategory.SAFE_BET.value]
    stretch_picks = [r for r in rows if r["category"] == EventCategory.STRETCH_PICK.value]

    write_csv(OUTPUT_DIR / "all_events.csv",     rows)
    write_csv(OUTPUT_DIR / "safe_bets.csv",      safe_bets)
    write_csv(OUTPUT_DIR / "stretch_picks.csv",  stretch_picks)

    # ── print summary ──
    def print_table(title: str, data: list[dict], n: int = 10) -> None:
        print(f"\n{'─'*60}")
        print(f"{title} ({len(data)} total)")
        print(f"{'─'*60}")
        if not data:
            print("  (none)")
            return
        for r in data[:n]:
            print(f"  {r['score']}  {r['date']:<12}  {r['venue']:<20}  {r['bill'][:45]}")
            print(f"         match: {r['driver_artist']} via {r['driver_mode']}")
        if len(data) > n:
            print(f"  … and {len(data) - n} more (see CSV)")

    print_table("SAFE BETS",     safe_bets)
    print_table("STRETCH PICKS", stretch_picks)

    print(f"\n{'─'*60}")
    print(f"FILES WRITTEN to debug/output/")
    print(f"  all_events.csv     ({len(rows)} events)")
    print(f"  safe_bets.csv      ({len(safe_bets)} events)")
    print(f"  stretch_picks.csv  ({len(stretch_picks)} events)")
    print(f"  clusters.json")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    spotify_user_id = sys.argv[1]
    print(f"\nInspecting data for user: {spotify_user_id}")

    init_db()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with get_session() as session:
        user = load_user(session, spotify_user_id)
        taste_modes = json.loads(user.taste_modes)

        # Load all artist records so we can show names in the cluster dump
        top_ids = json.loads(user.top_artist_ids)
        artists = session.exec(select(Artist).where(Artist.id.in_(top_ids))).all()
        artist_map = {a.id: a for a in artists}

        events, bills = load_upcoming_events(session)

    dump_clusters(taste_modes, artist_map)

    if not events:
        print("\n  No upcoming events in DB (next 60 days).")
        print("  → Run `just scrape` to populate events.")
        return

    print(f"\n  {len(events)} upcoming events loaded — scoring...")
    dump_events(events, bills, taste_modes)


if __name__ == "__main__":
    main()
