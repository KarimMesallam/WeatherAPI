import asyncio
import calendar
import json
from datetime import datetime
from unittest import mock

import numpy as np
import pytest
import httpx

import app.tides_fes2022 as fes
from app import main
from app.config import TIDE_DATUM_OFFSET_CM
from app.tide_schedule import build_tide_schedule

pytestmark = pytest.mark.skipif(
    not fes.CACHE_FILE.exists(), reason="FES2022 constants not installed"
)

START = calendar.timegm(datetime(2026, 10, 13, 0, 0).timetuple())


def hourly_from_conditions(base: datetime):
    class FixedNow(datetime):
        @classmethod
        def utcnow(cls):
            return base

    with mock.patch.object(fes, "datetime", FixedNow):
        return fes.compute_tides_fes2022()


def test_samples_match_hourly_conditions_tides():
    tide, tide_ts = hourly_from_conditions(datetime(2026, 10, 13, 0, 0))
    schedule = build_tide_schedule(tide_ts, 7)
    hourly = schedule["heights"][::6]
    assert len(hourly) == len(tide)
    assert all(abs(fine - whole) <= 0.55 for fine, whole in zip(hourly, tide))


def test_samples_cover_requested_days_at_ten_minutes():
    schedule = build_tide_schedule(START + 123, 2)
    assert schedule["start"] == START
    assert schedule["step"] == 600
    assert len(schedule["heights"]) == 2 * 144


def test_highs_and_lows_alternate_and_are_turning_points():
    schedule = build_tide_schedule(START, 7)
    events = sorted(
        [(e["t"], "high") for e in schedule["highs"]]
        + [(e["t"], "low") for e in schedule["lows"]]
    )
    kinds = [kind for _, kind in events]
    assert all(a != b for a, b in zip(kinds, kinds[1:]))
    for high in schedule["highs"]:
        around = fes.predict_tide_m(np.array([high["t"] - 600, high["t"], high["t"] + 600]))
        assert around[1] > around[0] and around[1] > around[2]


def test_slack_high_window_brackets_its_high():
    schedule = build_tide_schedule(START, 7)
    highs = {e["t"]: e["h"] for e in schedule["highs"]}
    assert len(schedule["slack_high"]) == len(highs)
    for window in schedule["slack_high"]:
        assert window["start"] < window["peak"] < window["end"]
        assert highs[window["peak"]] == window["h"]
        edges = fes.predict_tide_m(np.array([window["start"], window["end"]])) * 100
        peak = window["h"] - schedule["datum_offset_cm"]
        assert np.all(edges >= peak - schedule["slack_threshold_cm"] - 1)


def test_tides_endpoint():
    async def fetch(params):
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/tides", params=params)

    response = asyncio.run(fetch({"start": START, "days": 1}))
    assert response.status_code == 200
    assert response.json()["start"] == START
    assert asyncio.run(fetch({"days": 9})).status_code == 422


def test_gauge_calibration_is_applied():
    with open(fes.CACHE_FILE) as f:
        raw = json.load(f)
    with open(fes.CALIBRATION_FILE) as f:
        corrections = json.load(f)["constituents"]
    calibrated = fes._load_constants()
    m2 = raw["constituents"].index("m2")
    assert calibrated["amplitude"][m2] == pytest.approx(
        raw["amplitude"][m2] * corrections["m2"]["amplitude_ratio"])
    assert calibrated["phase"][m2] == pytest.approx(
        raw["phase"][m2] + corrections["m2"]["phase_shift_deg"])


def test_datum_is_lowest_astronomical_tide():
    start = calendar.timegm(datetime(2026, 1, 1).timetuple())
    epochs = start + 3600 * np.arange(19 * 8766)
    lowest_cm = fes.predict_tide_m(epochs).min() * 100
    assert abs(lowest_cm + TIDE_DATUM_OFFSET_CM) <= 1
