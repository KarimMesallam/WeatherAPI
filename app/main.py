import asyncio
import calendar
import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.cache import CacheManager
from app.config import BACKGROUND_CHECK_INTERVAL, TZ_OFFSET_MINUTES
from app.fetcher import (
    close_client,
    fetch_daily_dust,
    fetch_sea_temperature,
    fetch_weather,
)
from app.tides import compute_tides

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Dahab Marine Conditions API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

cache = CacheManager()
_refresh_lock = asyncio.Lock()


async def _do_refresh() -> Dict[str, Any]:
    """Fetch all data sources and assemble the response payload."""
    logger.info("Starting data refresh...")

    # Fetch weather, sea temp, and dust concurrently
    weather_data, sea_temp, dust_daily = await asyncio.gather(
        fetch_weather(),
        fetch_sea_temperature(),
        fetch_daily_dust(),
    )

    # Compute tides in a thread pool (CPU-bound)
    loop = asyncio.get_event_loop()
    tide_data = await loop.run_in_executor(None, compute_tides)

    # Compute Unix epoch of first forecast hour (UTC)
    # time[0] is local time like "2026-01-30T01:00", tz_offset is minutes ahead of UTC
    first_local = datetime.strptime(weather_data["time"][0], "%Y-%m-%dT%H:%M")
    ts = int(calendar.timegm(first_local.timetuple())) - TZ_OFFSET_MINUTES * 60

    result: Dict[str, Any] = {
        "ts": ts,
        "tz_offset": TZ_OFFSET_MINUTES,
        "time": weather_data["time"],
        "wind": weather_data["wind"],
        "wind_dir": weather_data["wind_dir"],
        "gust": weather_data["gust"],
        "temp": weather_data["temp"],
    }

    if dust_daily is not None:
        result["dust_daily"] = dust_daily

    if sea_temp is not None:
        result["sea_temp"] = sea_temp

    if tide_data is not None:
        result["tide"] = tide_data

    cache.update(result)
    logger.info("Data refresh complete")
    return result


async def refresh_if_needed() -> None:
    """Refresh data if the cache is stale. Uses a lock to prevent concurrent refreshes."""
    if not cache.needs_refresh:
        return
    async with _refresh_lock:
        # Double-check after acquiring lock
        if not cache.needs_refresh:
            return
        try:
            await _do_refresh()
        except Exception as exc:
            logger.error("Refresh failed: %s", exc, exc_info=True)


async def _background_poll() -> None:
    """Background loop that checks for staleness and refreshes."""
    while True:
        await asyncio.sleep(BACKGROUND_CHECK_INTERVAL)
        try:
            await refresh_if_needed()
        except Exception as exc:
            logger.error("Background poll error: %s", exc, exc_info=True)


@app.on_event("startup")
async def startup() -> None:
    logger.info("Starting Dahab Marine Conditions API")
    # Do initial fetch if cache is empty or stale
    try:
        await refresh_if_needed()
    except Exception as exc:
        logger.error("Initial fetch failed: %s", exc, exc_info=True)
    # Start background polling
    asyncio.ensure_future(_background_poll())
    logger.info("Background polling started")


@app.on_event("shutdown")
async def shutdown() -> None:
    await close_client()
    logger.info("Shutdown complete")


@app.get("/api/conditions")
async def get_conditions() -> JSONResponse:
    """Return current marine conditions data.

    Returns cached data immediately. Triggers background refresh if stale.
    """
    # Trigger background refresh if needed (non-blocking)
    asyncio.ensure_future(refresh_if_needed())

    response = cache.get_response()
    if response is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Data not yet available, try again shortly"},
        )
    return JSONResponse(content=response)


@app.get("/api/health")
async def health() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(
        content={
            "status": "ok" if cache.has_data else "warming_up",
            "has_data": cache.has_data,
            "cache_age_seconds": int(cache.get_age_seconds())
            if cache.has_data
            else None,
            "needs_refresh": cache.needs_refresh,
        }
    )
