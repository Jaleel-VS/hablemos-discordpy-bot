"""Tests for the pet feature: pure-function unit tests + route integration tests.

Route tests use FastAPI's TestClient with Discord identity and DB both stubbed
out (db=None), matching the pattern in test_routes.py.  Pure-function tests
exercise derive_mood and validate_choice directly.
"""
from __future__ import annotations

from datetime import date, timedelta

import app.pet as pet_mod
import pytest
from app.config import Settings
from app.main import create_app
from app.pet import COLORS, SPECIES, default_pet, derive_mood, validate_choice
from fastapi import HTTPException
from fastapi.testclient import TestClient

# ── derive_mood unit tests ─────────────────────────────────────────────────────

TODAY = date(2026, 10, 9)


def d(offset: int) -> date:
    """Return TODAY + offset days (negative = past)."""
    return TODAY + timedelta(days=offset)


class TestDeriveMood:
    def test_no_dates_idle(self):
        mood, streak, played = derive_mood([], TODAY)
        assert mood == "idle"
        assert streak == 0
        assert played is False

    def test_today_only_idle(self):
        mood, streak, played = derive_mood([TODAY], TODAY)
        assert mood == "idle"
        assert streak == 1
        assert played is True

    def test_today_plus_two_prior_happy(self):
        # streak of 3 → happy
        dates = [TODAY, d(-1), d(-2)]
        mood, streak, played = derive_mood(dates, TODAY)
        assert mood == "happy"
        assert streak == 3
        assert played is True

    def test_yesterday_only_waiting_streak_1(self):
        mood, streak, played = derive_mood([d(-1)], TODAY)
        assert mood == "waiting"
        assert streak == 1
        assert played is False

    def test_8_days_ago_sleepy(self):
        mood, streak, played = derive_mood([d(-8)], TODAY)
        assert mood == "sleepy"
        assert streak == 0
        assert played is False

    def test_gap_in_middle_breaks_streak(self):
        # Played today and 3 days ago but NOT yesterday or 2 days ago.
        # Streak from today = 1 (gap at d(-1)), so mood = idle (< 3).
        dates = [TODAY, d(-3)]
        mood, streak, played = derive_mood(dates, TODAY)
        assert mood == "idle"
        assert streak == 1
        assert played is True

    def test_waiting_streak_counts_from_yesterday(self):
        # yesterday + day before → streak 2, still waiting (< 3 for happy threshold
        # only applies to played_today path)
        dates = [d(-1), d(-2)]
        mood, streak, played = derive_mood(dates, TODAY)
        assert mood == "waiting"
        assert streak == 2
        assert played is False

    def test_yesterday_3_day_streak_still_waiting(self):
        # Not played today, but 3-day streak ending yesterday → waiting (not happy,
        # happy only triggers when played_today)
        dates = [d(-1), d(-2), d(-3)]
        mood, streak, played = derive_mood(dates, TODAY)
        assert mood == "waiting"
        assert streak == 3
        assert played is False

    def test_6_days_ago_not_sleepy(self):
        # 6 days ago < 7 day threshold → idle, not sleepy
        mood, streak, played = derive_mood([d(-6)], TODAY)
        assert mood == "idle"
        assert streak == 0
        assert played is False

    def test_exactly_7_days_ago_sleepy(self):
        mood, streak, played = derive_mood([d(-7)], TODAY)
        assert mood == "sleepy"
        assert streak == 0
        assert played is False


# ── validate_choice unit tests ────────────────────────────────────────────────

class TestValidateChoice:
    def test_valid_choice_returns_normalised(self):
        species, color, name = validate_choice("blob", "#5fc9b5", "  Blobby  ")
        assert species == "blob"
        assert color == "#5fc9b5"
        assert name == "Blobby"

    def test_invalid_species_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_choice("dragon", "#5fc9b5", "")
        assert exc_info.value.status_code == 400

    def test_invalid_color_no_hash_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_choice("blob", "5fc9b5", "")
        assert exc_info.value.status_code == 400

    def test_invalid_color_short_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_choice("blob", "#5fc9b", "")
        assert exc_info.value.status_code == 400

    def test_name_too_long_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_choice("blob", "#5fc9b5", "a" * 21)
        assert exc_info.value.status_code == 400

    def test_name_exactly_20_ok(self):
        _, _, name = validate_choice("orb", "#ffffff", "a" * 20)
        assert len(name) == 20

    def test_empty_name_ok(self):
        _, _, name = validate_choice("star", "#ff8fab", "")
        assert name == ""

    def test_all_species_valid(self):
        for sp in SPECIES:
            validate_choice(sp, "#aabbcc", "")  # should not raise


class TestDefaultPet:
    def test_stable_per_user(self):
        assert default_pet(123456789) == default_pet(123456789)

    def test_valid_and_unnamed(self):
        """The default must pass the same validation as a picked pet."""
        for uid in range(200):
            pet = default_pet(uid)
            assert validate_choice(pet["species"], pet["color"], pet["name"]) == (
                pet["species"], pet["color"], "",
            )

    def test_spreads_sequential_ids(self):
        """Consecutive snowflakes shouldn't all land on one species/colour."""
        base = 1_100_000_000_000_000_000
        pets = [default_pet(base + i) for i in range(200)]
        assert {p["species"] for p in pets} == set(SPECIES)
        assert {p["color"] for p in pets} == set(COLORS)


# ── route integration tests (db=None) ────────────────────────────────────────

@pytest.fixture
def pet_client(monkeypatch):
    """TestClient with Discord stubbed and db disabled."""
    async def fake_fetch_user(access_token: str):
        return {"id": "42", "username": "tester", "global_name": "", "avatar": ""}

    monkeypatch.setattr(pet_mod, "fetch_user", fake_fetch_user)

    cfg = Settings(
        discord_client_id="123",
        discord_client_secret="test-secret-for-sealing",
        port=8080,
        environment="test",
        static_dir="/tmp/nope",
        database_url="",  # no DB
    )
    app = create_app(cfg)
    with TestClient(app) as c:
        yield c


class TestPetRoutes:
    def test_me_without_choice_returns_default(self, pet_client):
        r = pet_client.post("/api/pet/me", json={"access_token": "t"})
        assert r.status_code == 200
        body = r.json()
        assert body["pet"] == default_pet(42)
        assert body["mood"] == "idle"
        assert body["streak_days"] == 0
        assert body["played_today"] is False
        assert body["games_this_week"] == 0
        assert body["favorite_game"] is None

    def test_choose_valid_echoes_pet(self, pet_client):
        r = pet_client.post(
            "/api/pet/choose",
            json={"access_token": "t", "species": "blob", "color": "#5fc9b5", "name": "Blobby"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["pet"] == {"species": "blob", "color": "#5fc9b5", "name": "Blobby"}
        # zero stats because db is None
        assert body["streak_days"] == 0
        assert body["played_today"] is False

    def test_choose_bad_species_400(self, pet_client):
        r = pet_client.post(
            "/api/pet/choose",
            json={"access_token": "t", "species": "dragon", "color": "#5fc9b5"},
        )
        assert r.status_code == 400

    def test_choose_bad_color_400(self, pet_client):
        r = pet_client.post(
            "/api/pet/choose",
            json={"access_token": "t", "species": "blob", "color": "not-a-color"},
        )
        assert r.status_code == 400

    def test_choose_name_too_long_400(self, pet_client):
        r = pet_client.post(
            "/api/pet/choose",
            json={"access_token": "t", "species": "orb", "color": "#aabbcc", "name": "x" * 21},
        )
        assert r.status_code == 400

    def test_choose_name_stripped_and_echoed(self, pet_client):
        r = pet_client.post(
            "/api/pet/choose",
            json={"access_token": "t", "species": "ghost", "color": "#c9a0ff", "name": "  Ghosty  "},
        )
        assert r.status_code == 200
        assert r.json()["pet"]["name"] == "Ghosty"

    def test_choose_empty_name_ok(self, pet_client):
        r = pet_client.post(
            "/api/pet/choose",
            json={"access_token": "t", "species": "pebble", "color": "#9be7ff"},
        )
        assert r.status_code == 200
        assert r.json()["pet"]["name"] == ""
