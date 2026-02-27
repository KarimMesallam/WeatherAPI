# Dahab Marine Conditions API

Backend API server providing compact marine conditions data for a Garmin watch app. Serves wind, tide, weather, and sea temperature forecasts for Dahab, Egypt (Gulf of Aqaba, Red Sea).

**Live endpoint:** `https://dahab-api.karimmesallam.com/api/conditions`

## Architecture

```
Garmin Mk3i Watch
    └─ HTTPS GET (every ~30min) ─→ dahab-api.karimmesallam.com
                                        │
                                   nginx (SSL termination)
                                        │
                                   FastAPI (uvicorn, port 8000)
                                        │
                          ┌─────────────┼─────────────┐
                          │             │             │
                    Open-Meteo    Open-Meteo     pyTMD + GOT4.10
                    Weather API   Marine API     Tide Model (local)
                    (wind, temp,  (sea temp)     (tide heights)
                     gusts, vis)
```

- **Cache-first**: Responses are always served from cache. Background polling refreshes every 30 minutes.
- **Disk-backed**: Cache persists to `data/cache.json` and survives restarts.
- **Stale-safe**: If upstream APIs are down, stale data is served with an `age` field indicating staleness.

## API Reference

### `GET /api/conditions`

Returns a single JSON object (~4.5KB) with hourly and daily forecast data. All numeric values are integers for compact transfer (well under the Garmin 16KB limit).

**Response fields:**

| Field       | Type       | Length | Unit/Description                              |
|-------------|------------|--------|-----------------------------------------------|
| `ts`        | `int`      | —      | Unix epoch (seconds) of first forecast hour, in UTC |
| `tz_offset` | `int`      | —      | Local timezone offset from UTC in minutes (120 = UTC+2) |
| `time`      | `string[]` | 168    | ISO 8601 timestamps, local time (`2026-01-30T01:00`) |
| `wind`      | `int[]`    | 168    | Wind speed at 10m in **knots**                |
| `wind_dir`  | `int[]`    | 168    | Wind direction in degrees (0-360, meteorological convention) |
| `gust`      | `int[]`    | 168    | Wind gusts at 10m in **knots**                |
| `temp`      | `int[]`    | 168    | Air temperature in Celsius                    |
| `dust_daily` | `int[]`   | 5-7    | Daily max Saharan dust concentration in ug/m3 (today + up to 6 days, may be absent) |
| `sea_temp`  | `int[]`    | 168    | Sea surface temperature in Celsius (may be absent) |
| `tide`      | `int[]`    | 168    | Tide height in centimeters relative to mean sea level (may be absent) |
| `age`       | `int`      | —      | Seconds since last successful data refresh    |

Hourly arrays (168 elements) cover 7 days. `dust_daily` (5-7 elements) covers up to 7 days — each value is the worst-case (maximum) dust concentration for that day, sourced from the Open-Meteo Air Quality API.

**Sample response** (truncated to 6 hours):

```json
{
  "ts": 1769727600,
  "tz_offset": 120,
  "time": ["2026-01-30T01:00", "2026-01-30T02:00", "2026-01-30T03:00", "..."],
  "wind":      [2, 2, 1, 2, 1, 2],
  "wind_dir":  [139, 143, 149, 157, 171, 187],
  "gust":      [4, 5, 4, 4, 4, 5],
  "temp":      [15, 15, 15, 15, 15, 14],
  "dust_daily": [171, 139, 203, 135, 242, 86],
  "sea_temp":  [22, 22, 22, 22, 22, 22],
  "tide":      [5, 18, 27, 28, 23, 12],
  "age": 150
}
```

### `GET /api/health`

```json
{
  "status": "ok",
  "has_data": true,
  "cache_age_seconds": 150,
  "needs_refresh": false
}
```

## Project Structure

```
/var/www/dahab-api/
├── app/
│   ├── __init__.py
│   ├── main.py         # FastAPI app, endpoints, startup, background polling
│   ├── fetcher.py      # Open-Meteo weather + marine API calls (async httpx)
│   ├── tides.py        # pyTMD tide computation (GOT4.10 model, sync/CPU-bound)
│   ├── cache.py        # In-memory + atomic disk-persisted cache
│   └── config.py       # All constants (coords, URLs, intervals, paths)
├── data/
│   └── cache.json      # Persistent cache (auto-generated)
├── tide-models/
│   └── GOT4.10c/       # NASA Goddard Ocean Tide model data (~42MB)
├── nginx.conf          # Reference nginx config (installed to /etc/nginx/sites-available/)
├── requirements.txt
├── venv/               # Python 3.8 virtual environment
└── README.md
```

## Data Sources

| Source | API | Rate Limit | Notes |
|--------|-----|-----------|-------|
| Wind, temp, gusts | [Open-Meteo Forecast](https://open-meteo.com/en/docs) | Free, no API key | Wind in knots via `wind_speed_unit=kn` |
| Daily dust | [Open-Meteo Air Quality](https://open-meteo.com/en/docs/air-quality-api) | Free, no API key | Saharan dust aerosol, 7-day hourly fetch, aggregated to daily max |
| Sea surface temperature | [Open-Meteo Marine](https://open-meteo.com/en/docs/marine-weather-api) | Free, no API key | Covers Gulf of Aqaba |
| Tides | [pyTMD](https://github.com/tsutterley/pyTMD) + GOT4.10c | Local computation | NASA model, extrapolation enabled for Red Sea |

**Tide model**: GOT4.10c (Goddard Ocean Tide) from [NASA GSFC](https://earth.gsfc.nasa.gov/geo/data/ocean-tide-models). The Gulf of Aqaba has a small tidal range (~0.5-1m), and the 0.5-degree GOT grid doesn't directly cover Dahab's narrow coastline, so extrapolation is used. Results are approximate but show correct tidal patterns.

## Infrastructure

- **Server**: Contabo VPS (161.97.85.53), Ubuntu 20.04, Python 3.8.10
- **Process manager**: PM2 (`DahabAPI` process)
- **Reverse proxy**: nginx with Let's Encrypt SSL
- **Domain**: `dahab-api.karimmesallam.com`
- **Internal port**: 8000 (uvicorn, single worker)

### PM2 Commands

```bash
pm2 status DahabAPI          # Check status
pm2 logs DahabAPI            # View logs
pm2 restart DahabAPI         # Restart
pm2 stop DahabAPI            # Stop
```

### Configuration

All configuration is in `app/config.py`:

- **Coordinates**: 28.4937N, 34.5131E (Dahab)
- **Poll interval**: 30 minutes
- **Forecast window**: 168 hours (7 days)
- **Timezone**: UTC+2 (Egypt Standard Time)
- **Tide model**: GOT4.10 via pyTMD 2.1.0

## Development

```bash
cd /var/www/dahab-api
source venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Dependencies

```
fastapi==0.104.1      # Last version supporting Python 3.8
pydantic>=1.10,<2.0   # v1 for Python 3.8 compat
uvicorn[standard]==0.24.0
httpx>=0.25,<1.0      # Async HTTP client
numpy<2.0
scipy<2.0
pyTMD==2.1.0          # v2.1.0 (later versions require Python 3.9+)
```
