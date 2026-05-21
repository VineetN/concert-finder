"""Tests for pure parsing helpers in the scraper modules — no HTTP calls."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest

from concert_finder_ingest.scrapers.barboza import _parse_barboza_date, _parse_openers
from concert_finder_ingest.scrapers.ticketweb import _extract_jsonld
from concert_finder_ingest.scrapers.tractor import _parse_tractor_date, _split_artists


# ── Tractor Tavern: date parsing ──────────────────────────────────────────────

class TestParseTractorDate:
    def test_full_month_name(self):
        result = _parse_tractor_date("May 21 @ 08:00 PM")
        assert result is not None
        dt = date.fromisoformat(result)
        assert dt.month == 5
        assert dt.day == 21

    def test_abbreviated_month(self):
        result = _parse_tractor_date("Jun 3 @ 07:30 PM")
        assert result is not None
        dt = date.fromisoformat(result)
        assert dt.month == 6
        assert dt.day == 3

    def test_year_rollover_for_past_date(self):
        # A date that's already passed this year should roll to next year
        past = datetime.now() - timedelta(days=60)
        text = past.strftime("%B %d @ 08:00 PM")
        result = _parse_tractor_date(text)
        assert result is not None
        dt = date.fromisoformat(result)
        assert dt.year == datetime.now().year + 1

    def test_future_date_stays_this_year(self):
        future = datetime.now() + timedelta(days=30)
        text = future.strftime("%B %d @ 08:00 PM")
        result = _parse_tractor_date(text)
        assert result is not None
        dt = date.fromisoformat(result)
        assert dt.year == datetime.now().year

    def test_returns_iso_format(self):
        result = _parse_tractor_date("July 4 @ 09:00 PM")
        assert result is not None
        # Should be parseable as ISO date
        date.fromisoformat(result)

    def test_garbage_input_returns_none(self):
        assert _parse_tractor_date("not a date") is None

    def test_empty_string_returns_none(self):
        assert _parse_tractor_date("@ 08:00 PM") is None


# ── Tractor Tavern: artist splitting ─────────────────────────────────────────

class TestSplitArtists:
    def test_single_artist(self):
        headliner, openers = _split_artists("The Strokes")
        assert headliner == "The Strokes"
        assert openers == []

    def test_headliner_and_one_opener(self):
        headliner, openers = _split_artists("Radiohead, Thom Yorke")
        assert headliner == "Radiohead"
        assert openers == ["Thom Yorke"]

    def test_headliner_and_multiple_openers(self):
        headliner, openers = _split_artists("Band A, Band B, Band C")
        assert headliner == "Band A"
        assert openers == ["Band B", "Band C"]

    def test_strips_whitespace(self):
        headliner, openers = _split_artists("  Artist X ,  Artist Y  ")
        assert headliner == "Artist X"
        assert openers == ["Artist Y"]

    def test_empty_segments_ignored(self):
        headliner, openers = _split_artists("Band, , Support")
        assert headliner == "Band"
        assert openers == ["Support"]


# ── Barboza: date parsing ─────────────────────────────────────────────────────

class TestParseBarbozaDate:
    def test_full_month_name(self):
        assert _parse_barboza_date("May 22 2026") == "2026-05-22"

    def test_abbreviated_month(self):
        assert _parse_barboza_date("Jun 5 2026") == "2026-06-05"

    def test_leading_trailing_whitespace(self):
        assert _parse_barboza_date("  July 4 2026  ") == "2026-07-04"

    def test_december(self):
        assert _parse_barboza_date("December 31 2026") == "2026-12-31"

    def test_garbage_returns_none(self):
        assert _parse_barboza_date("tomorrow") is None

    def test_empty_string_returns_none(self):
        assert _parse_barboza_date("") is None


# ── Barboza: opener parsing ───────────────────────────────────────────────────

class TestParseOpeners:
    def test_plus_separator(self):
        assert _parse_openers("Band A + Band B") == ["Band A", "Band B"]

    def test_comma_separator(self):
        assert _parse_openers("Band A, Band B") == ["Band A", "Band B"]

    def test_strips_leading_with(self):
        assert _parse_openers("with Band A + Band B") == ["Band A", "Band B"]

    def test_strips_leading_With_case_insensitive(self):
        assert _parse_openers("With Artist X") == ["Artist X"]

    def test_single_artist(self):
        assert _parse_openers("Solo Act") == ["Solo Act"]

    def test_empty_string(self):
        assert _parse_openers("") == []

    def test_three_artists(self):
        result = _parse_openers("A + B + C")
        assert result == ["A", "B", "C"]


# ── TicketWeb: JSON-LD extraction ─────────────────────────────────────────────

def _make_jsonld_html(events: list[dict]) -> str:
    blob = json.dumps(events)
    return f"<html><body><script type='application/ld+json'>{blob}</script></body></html>"


class TestExtractJsonld:
    def test_extracts_music_events(self):
        events = [{"@type": "MusicEvent", "name": "Test Show"}]
        html = _make_jsonld_html(events)
        result = _extract_jsonld(html)
        assert result == events

    def test_returns_empty_for_no_script(self):
        assert _extract_jsonld("<html><body></body></html>") == []

    def test_returns_empty_for_non_music_event_script(self):
        # Script present but no MusicEvent keyword
        html = "<html><body><script>[{\"@type\":\"WebPage\"}]</script></body></html>"
        assert _extract_jsonld(html) == []

    def test_returns_empty_for_malformed_json(self):
        html = '<html><body><script>[{bad json "MusicEvent"}</script></body></html>'
        result = _extract_jsonld(html)
        assert result == []

    def test_multiple_events_returned(self):
        events = [
            {"@type": "MusicEvent", "name": "Show 1"},
            {"@type": "MusicEvent", "name": "Show 2"},
        ]
        html = _make_jsonld_html(events)
        result = _extract_jsonld(html)
        assert len(result) == 2
        assert result[0]["name"] == "Show 1"

    def test_ignores_scripts_without_music_event_keyword(self):
        other_script = '<script type="application/ld+json">{"@type":"Organization"}</script>'
        music_script = f'<script>[{{"@type":"MusicEvent","name":"Gig"}}]</script>'
        html = f"<html><body>{other_script}{music_script}</body></html>"
        result = _extract_jsonld(html)
        assert len(result) == 1
        assert result[0]["name"] == "Gig"
