"""
One-time migration: normalize venue names in the DB and deduplicate events.

Run with:  uv run python scripts/normalize_venues.py

What it does:
  1. Renames non-canonical venue names to their canonical forms.
  2. Recomputes event IDs (which are hashes of date + venue + headliner).
  3. For events that become duplicates after renaming, migrates EventArtist
     links to the surviving event and deletes the duplicate.

Safe to re-run: already-canonical events are skipped.
"""
from __future__ import annotations

import hashlib
import sqlite3
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Resolve DB path the same way the app does
_db_url = os.environ.get("DATABASE_URL", "data/concert.db")
DB_PATH = _db_url.replace("sqlite:///", "").replace("sqlite://", "")

CANONICAL: dict[str, str] = {
    "tractor": "Tractor Tavern",
    "showbox sodo": "Showbox SoDo",
    "showbox at the market": "The Showbox",
    "chateau ste michelle winery": "Chateau Ste. Michelle Winery",
    "wamu theater": "WaMu Theater",
    "marymoor live - presented by toyota": "Marymoor Live",
    "moore theatre": "The Moore Theatre",
    "neptune theatre": "The Neptune Theatre",
    "paramount theatre": "The Paramount Theatre",
    "5th avenue theatre": "The 5th Avenue Theatre",
    "federal way paec": "Federal Way Performing Arts and Event Center",
    "fisher pavilion at seattle center": "Fisher Pavilion, Seattle Center",
    "fisher pavilion": "Fisher Pavilion, Seattle Center",
    "benaroya hall - s. mark taper auditorium": "Benaroya Hall",
    "s. mark taper auditorium, benaroya hall": "Benaroya Hall",
    "taper auditorium": "Benaroya Hall",
    "the tulalip amphitheatre": "Tulalip Amphitheatre",
    "the vera project": "Vera Project",
    "victory hall": "Victory Hall at The Boxyard",
    "ballard homestead (abbey arts)": "Ballard Homestead",
    "admiral theatre - wa": "Admiral Theatre",
}


def normalize(venue: str) -> str:
    return CANONICAL.get(venue.strip().lower(), venue.strip())


def new_event_id(date_str: str, venue: str, headliner: str) -> str:
    key = f"{date_str}|{venue.lower()}|{headliner.lower()}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def main() -> None:
    print(f"Connecting to {DB_PATH}")
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    cur = con.cursor()

    # Fetch all events with their headliner (billing_position = 0)
    cur.execute("""
        SELECT e.id, e.venue, date(e.date) as date_str, a.name as headliner
        FROM event e
        JOIN eventartist ea ON ea.event_id = e.id AND ea.billing_position = 0
        JOIN artist a ON a.id = ea.artist_id
    """)
    events = cur.fetchall()
    print(f"Total events with headliner: {len(events)}")

    renamed = 0
    merged = 0
    skipped = 0

    for event_id, venue, date_str, headliner in events:
        canonical = normalize(venue)
        if canonical == venue:
            skipped += 1
            continue

        canonical_id = new_event_id(date_str, canonical, headliner)

        # Check if canonical event already exists
        cur.execute("SELECT id FROM event WHERE id = ?", (canonical_id,))
        existing = cur.fetchone()

        if existing:
            # Duplicate — migrate EventArtist links then delete this event
            cur.execute("SELECT artist_id, billing_position FROM eventartist WHERE event_id = ?", (event_id,))
            links = cur.fetchall()
            for artist_id, billing_pos in links:
                cur.execute(
                    "SELECT 1 FROM eventartist WHERE event_id = ? AND artist_id = ?",
                    (canonical_id, artist_id),
                )
                if not cur.fetchone():
                    cur.execute(
                        "INSERT INTO eventartist (event_id, artist_id, billing_position) VALUES (?, ?, ?)",
                        (canonical_id, artist_id, billing_pos),
                    )
            cur.execute("DELETE FROM eventartist WHERE event_id = ?", (event_id,))
            cur.execute("DELETE FROM event WHERE id = ?", (event_id,))
            merged += 1
        else:
            # No canonical event yet — update EventArtist FK then update Event id + venue
            cur.execute("UPDATE eventartist SET event_id = ? WHERE event_id = ?", (canonical_id, event_id))
            cur.execute("UPDATE event SET id = ?, venue = ? WHERE id = ?", (canonical_id, canonical, event_id))
            renamed += 1

    con.commit()
    con.close()

    print(f"Renamed:  {renamed} events (venue updated, new ID assigned)")
    print(f"Merged:   {merged} duplicate events removed")
    print(f"Skipped:  {skipped} events already canonical")
    print("Done.")


if __name__ == "__main__":
    main()
