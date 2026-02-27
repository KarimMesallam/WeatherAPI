# Next Phase: Garmin Watch App (Monkey C)

Instructions for building the Garmin Descent Mk3i watch app that displays marine conditions from the Dahab API.

## Context for Claude Code

Use this prompt to start the next phase on your personal machine:

---

**Prompt:**

> I need to build a Garmin watch app (Monkey C / Connect IQ) for my Descent Mk3i dive watch that displays marine conditions for Dahab, Egypt. The backend API is already running.
>
> **API endpoint:** `https://dahab-api.karimmesallam.com/api/conditions`
>
> The API returns a single JSON object (~6KB) with 168 hourly forecast values (7 days). All numeric arrays are integers. Here's the schema:
>
> | Field      | Type       | Unit                                          |
> |------------|------------|-----------------------------------------------|
> | `ts`       | `int`      | Unix epoch (seconds) of first forecast hour, in UTC |
> | `tz_offset`| `int`      | Local timezone offset from UTC in minutes (120 = UTC+2) |
> | `time`     | `string[]` | ISO timestamps, local time (`2026-01-30T01:00`) |
> | `wind`     | `int[]`    | Wind speed in knots                           |
> | `wind_dir` | `int[]`    | Wind direction in degrees (0-360)             |
> | `gust`     | `int[]`    | Wind gusts in knots                           |
> | `temp`     | `int[]`    | Air temperature in Celsius                    |
> | `dust_daily`| `int[]`   | Daily max Saharan dust in ug/m3 (5-7 days)    |
> | `sea_temp` | `int[]`    | Sea surface temperature in Celsius            |
> | `tide`     | `int[]`    | Tide height in cm (relative to MSL)           |
> | `age`      | `int`      | Seconds since last data refresh               |
>
> Hourly arrays are length 168 (7 days). `dust_daily` is length 5-7 (one max-dust per day, depends on model availability). Index 0 = first forecast hour / today.
>
> **Watch:** Garmin Descent Mk3i (416x416 AMOLED round display, Connect IQ 7.x)
>
> **App requirements:**
> 1. Fetch data from the API on app open and periodically in background
> 2. Main screen: current conditions summary (wind speed+direction, temp, sea temp, tide height, visibility as text)
> 3. Scrollable graphs: wind speed (with gust overlay), tide height, temperature — each showing 48-72 hours
> 4. Current time marker (vertical line) on graphs so I can see "now" vs forecast
> 5. Wind direction shown as compass arrows or abbreviations (N, NE, E, etc.)
> 6. Color coding: wind speed green (<10kn), yellow (10-15kn), red (>15kn)
> 7. Handle offline gracefully — show last cached data with "age" indicator
> 8. Data refresh: pull new data every 30 minutes (matches server cache interval)
>
> **Garmin constraints to keep in mind:**
> - 16KB max HTTP response (API returns ~5KB, no issue)
> - 128KB memory limit for apps — parse JSON carefully, don't keep full string in memory
> - No floating point in older CIQ — all API values are already integers
> - `Communications.makeWebRequest()` for HTTP calls
> - Background service (`ServiceDelegate`) for periodic updates
> - Use `WatchUi.View` and `onUpdate(dc)` for drawing
> - Round display: 416x416 pixels, use `Dc` drawing primitives for graphs

---

## API Details for the Watch App

### Live endpoint

```
GET https://dahab-api.karimmesallam.com/api/conditions
```

- CORS enabled (`Access-Control-Allow-Origin: *`)
- No authentication required
- Response is ~6KB JSON (well within Garmin's 16KB limit)
- Server refreshes data every 30 minutes
- If server cache is stale, `age` value will be >1800

### Sample response

```json
{
  "ts": 1769727600,
  "tz_offset": 120,
  "time": ["2026-01-30T01:00", "2026-01-30T02:00", "...120 entries..."],
  "wind":     [2, 2, 1, 2, 1, 2, 3, 5, 8, 12, 15, 14, "..."],
  "wind_dir": [139, 143, 149, 157, 171, 187, 200, 210, "..."],
  "gust":     [4, 5, 4, 4, 4, 5, 7, 10, 14, 18, 22, 20, "..."],
  "temp":     [15, 15, 15, 15, 15, 14, 14, 16, 19, 22, 24, 24, "..."],
  "dust_daily": [171, 139, 203, 135, 242, 86],
  "sea_temp": [22, 22, 22, 22, "..."],
  "tide":     [5, 18, 27, 28, 23, 12, -2, -15, -23, -25, -20, -10, "..."],
  "age": 150
}
```

### Key data characteristics

- **Wind**: Typical Dahab range 0-25kn, occasionally 30+. Thermals kick in mid-morning.
- **Gusts**: Usually 1.5-2x wind speed. Important for kitesurfing/diving decisions.
- **Tide**: Gulf of Aqaba has small range: roughly -50cm to +50cm. Shown in cm relative to MSL.
- **Dust**: Daily max Saharan dust in ug/m3 (5-7 values). <50 is clean, 50-200 is moderate, >200 is a dust storm. Directly impacts both air visibility and underwater clarity in Dahab.
- **Sea temp**: 20-28C depending on season. Important for wetsuit choice.
- **Time**: Local timestamps (UTC+2). The `tz_offset` field (120 minutes) confirms this.

### Finding "current hour" index

The `ts` field is the Unix epoch (UTC) of index 0. Each subsequent index is +3600 seconds. To find the index for "now":

```
// Monkey C pseudocode
var nowUtc = Time.now().value();  // Unix epoch seconds
var currentIndex = (nowUtc - data.ts) / 3600;
if (currentIndex < 0) { currentIndex = 0; }
if (currentIndex >= data.wind.size()) { currentIndex = data.wind.size() - 1; }
```

No string parsing needed — pure integer math.

## Suggested App Architecture

```
DahabApp/
├── source/
│   ├── DahabApp.mc          # AppBase — handles lifecycle
│   ├── DahabView.mc         # Main view — current conditions summary
│   ├── DahabDelegate.mc     # Input delegate — handle scroll/swipe
│   ├── GraphView.mc         # Graph drawing view (wind, tide, temp)
│   ├── DataManager.mc       # HTTP fetch, JSON parse, data storage
│   └── Util.mc              # Helpers (wind direction → text, color coding)
├── resources/
│   ├── strings.xml
│   ├── settings.xml         # App settings (refresh interval, etc.)
│   └── drawables.xml
├── manifest.xml              # Target: descentmk3i, permissions: Communications
└── monkey.jungle             # Build config
```

### View Flow

```
[App Open]
    │
    ├─→ DahabView (main summary)
    │     Wind: 12 kn NW  Gust: 18 kn
    │     Temp: 24C  Sea: 22C
    │     Tide: +15cm  Vis: 24km
    │     (age indicator if stale)
    │
    ├─→ [Scroll/Swipe Down] → Wind Graph (48-72h)
    │     Y-axis: 0-30 kn
    │     Blue line: wind, Red fill: gusts
    │     Vertical "now" line
    │     Green/yellow/red zones
    │
    ├─→ [Scroll/Swipe Down] → Tide Graph (48-72h)
    │     Y-axis: -50 to +50 cm
    │     Blue curve with fill
    │     Zero line (MSL) marked
    │
    └─→ [Scroll/Swipe Down] → Temp Graph (48-72h)
          Y-axis: auto-scaled
          Air temp + sea temp overlay
```

### Graph Drawing Tips (416x416 AMOLED)

- **Graph area**: Leave ~40px top (title), ~30px bottom (time labels), ~40px left (Y-axis labels)
- **Usable graph**: ~336 x 346 pixels
- **48 hours**: Each hour = 7 pixels wide. Good density.
- **72 hours**: Each hour = ~4.7 pixels. Still readable on AMOLED.
- **"Now" marker**: Bright vertical line at current hour index
- **Day boundaries**: Faint vertical lines at midnight to show day transitions
- **Wind color zones**: Draw horizontal bands (green 0-10, yellow 10-15, red 15+) behind the graph

### Memory Considerations

The 128KB app memory limit is tight. Strategies:

1. **Don't store raw JSON string** — parse directly into typed arrays
2. **Only keep 72 hours** — discard hours 73-120 after parsing to save memory
3. **Use `Application.Storage`** for persistence between app launches
4. **Integer arrays only** — the API already returns integers, no float conversion needed
5. **Share arrays** — wind, gust, tide etc. are just `Array<Number>`, no wrapper objects needed

### Background Service

For periodic updates without the app being in the foreground:

```
// In manifest.xml, add:
// <iq:background>
//   <iq:service class="DahabService" />
// </iq:background>

class DahabService extends System.ServiceDelegate {
    function onTemporalEvent() {
        // Called by system on schedule
        // Fetch new data, store in Application.Storage
    }
}
```

Register in AppBase:
```
Background.registerForTemporalEvent(new Time.Duration(1800));  // 30 min
```

## Development Setup

### Prerequisites

1. [Connect IQ SDK](https://developer.garmin.com/connect-iq/sdk/) (latest)
2. [Visual Studio Code](https://code.visualstudio.com/) + [Monkey C Extension](https://marketplace.visualstudio.com/items?itemName=garmin.monkey-c)
3. Or use the command-line SDK tools directly

### Build & Test

```bash
# Set SDK path
export CIQ_HOME=/path/to/connectiq-sdk

# Build for simulator
monkeyc -d descentmk3i -f monkey.jungle -o bin/DahabApp.prg

# Run in simulator
connectiq &  # Launch simulator
monkeydo bin/DahabApp.prg descentmk3i
```

### Deploy to Watch

1. Build a release `.iq` file
2. Transfer via Garmin Express or USB to `GARMIN/APPS/` on the watch
3. Or publish to Connect IQ Store for OTA install

## Health Check

Verify the API is still running before starting app development:

```bash
curl https://dahab-api.karimmesallam.com/api/health
# Expected: {"status":"ok","has_data":true,"cache_age_seconds":...,"needs_refresh":false}

curl https://dahab-api.karimmesallam.com/api/conditions | wc -c
# Expected: ~5200 bytes

curl https://dahab-api.karimmesallam.com/api/conditions | python3 -m json.tool | head -20
# Should show valid JSON with integer arrays
```
