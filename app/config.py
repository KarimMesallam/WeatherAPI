import os

# Dahab, Egypt coordinates
LATITUDE = 28.4937
LONGITUDE = 34.5131

# Open-Meteo API URLs
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
MARINE_API_URL = "https://marine-api.open-meteo.com/v1/marine"
AIR_QUALITY_API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# Weather API query parameters
WEATHER_PARAMS = {
    "latitude": LATITUDE,
    "longitude": LONGITUDE,
    "hourly": ",".join([
        "wind_speed_10m",
        "wind_direction_10m",
        "wind_gusts_10m",
        "temperature_2m",
    ]),
    "wind_speed_unit": "kn",
    "forecast_days": 7,
    "timezone": "auto",
}

# Marine API query parameters
MARINE_PARAMS = {
    "latitude": LATITUDE,
    "longitude": LONGITUDE,
    "hourly": "sea_surface_temperature",
    "forecast_days": 7,
    "timezone": "auto",
}

# Air Quality API query parameters (7 days for daily dust aggregation)
DUST_PARAMS = {
    "latitude": LATITUDE,
    "longitude": LONGITUDE,
    "hourly": "dust",
    "forecast_days": 7,
    "timezone": "auto",
}

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(BASE_DIR, "data", "cache.json")
TIDE_MODEL_DIR = os.path.join(BASE_DIR, "tide-models")

# Polling
POLL_INTERVAL_SECONDS = 1800  # 30 minutes
BACKGROUND_CHECK_INTERVAL = 60  # seconds between staleness checks

# Forecast
FORECAST_HOURS = 168

# Timezone offset for Dahab (UTC+2, Egypt Standard Time)
TZ_OFFSET_MINUTES = 120

# HTTP client
HTTP_TIMEOUT_SECONDS = 30

# Tide model configuration
# Options: "GOT4.10" (default, works but low resolution) or "FES2022" (better resolution)
TIDE_MODEL_NAME = os.environ.get("TIDE_MODEL", "GOT4.10")

# Datum offset: Models output relative to MSL, but tide tables use chart datum
# (Lowest Astronomical Tide). For Dahab, the offset is ~45cm based on comparison
# with tide-forecast.com. This shifts our values to match what divers/sailors expect.
TIDE_DATUM_OFFSET_CM = 45
