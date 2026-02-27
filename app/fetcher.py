import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config import (
    AIR_QUALITY_API_URL,
    DUST_PARAMS,
    HTTP_TIMEOUT_SECONDS,
    MARINE_API_URL,
    MARINE_PARAMS,
    WEATHER_API_URL,
    WEATHER_PARAMS,
)

logger = logging.getLogger(__name__)

_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None


def _to_int_list(values: List[Any]) -> List[int]:
    return [int(round(float(v))) if v is not None else 0 for v in values]


async def fetch_weather() -> Dict[str, Any]:
    """Fetch weather forecast from Open-Meteo.

    Returns dict with integer arrays for:
        time, wind, wind_dir, gust, temp
    """
    client = get_client()
    resp = await client.get(WEATHER_API_URL, params=WEATHER_PARAMS)
    resp.raise_for_status()
    data = resp.json()
    hourly = data["hourly"]

    return {
        "time": hourly["time"],
        "wind": _to_int_list(hourly["wind_speed_10m"]),
        "wind_dir": _to_int_list(hourly["wind_direction_10m"]),
        "gust": _to_int_list(hourly["wind_gusts_10m"]),
        "temp": _to_int_list(hourly["temperature_2m"]),
    }


async def fetch_daily_dust() -> Optional[List[int]]:
    """Fetch 7 days of hourly dust concentration and compute daily maximums.

    Uses the Open-Meteo Air Quality API (Saharan dust aerosol).
    Returns list of up to 7 integers (ug/m3) — one max-dust per day — or None on failure.
    Days with no data are omitted from the tail.
    """
    try:
        client = get_client()
        resp = await client.get(AIR_QUALITY_API_URL, params=DUST_PARAMS)
        resp.raise_for_status()
        data = resp.json()
        hourly_dust = data["hourly"]["dust"]

        # Group into 24-hour chunks and take the maximum of each day
        daily_max: List[int] = []
        for day in range(7):
            start = day * 24
            end = start + 24
            chunk = [v for v in hourly_dust[start:end] if v is not None]
            if chunk:
                daily_max.append(int(round(max(chunk))))
        return daily_max if daily_max else None
    except Exception as exc:
        logger.warning("Failed to fetch daily dust: %s", exc)
        return None


async def fetch_sea_temperature() -> Optional[List[int]]:
    """Fetch sea surface temperature from Open-Meteo Marine API.

    Returns list of integer temperatures (Celsius) or None on failure.
    """
    try:
        client = get_client()
        resp = await client.get(MARINE_API_URL, params=MARINE_PARAMS)
        resp.raise_for_status()
        data = resp.json()
        hourly = data["hourly"]
        return _to_int_list(hourly["sea_surface_temperature"])
    except Exception as exc:
        logger.warning("Failed to fetch sea temperature: %s", exc)
        return None
