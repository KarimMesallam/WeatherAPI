"""Minute-accurate tide schedule for dive planning.

Builds 10-minute samples, highs, lows and slack-high windows from the same
FES2022 prediction that feeds /api/conditions.
"""
from functools import lru_cache
from typing import Any, Dict, List

import numpy as np
from scipy.ndimage import maximum_filter1d, minimum_filter1d

from app.config import SLACK_HIGH_THRESHOLD_CM, TIDE_DATUM_OFFSET_CM
from app.tides_fes2022 import predict_tide_m

SAMPLE_STEP_SECONDS = 600
GRID_STEP_SECONDS = 60
TURNING_WINDOW_SECONDS = 6 * 3600  # +/-6 h, as on the watch
MAX_DAYS = 8


def _runs(mask: np.ndarray) -> List[range]:
    """Return index ranges of consecutive True values."""
    edges = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    return [range(int(s), int(e)) for s, e in zip(starts, ends)]


@lru_cache(maxsize=32)
def build_tide_schedule(start: int, days: int) -> Dict[str, Any]:
    """Tide schedule for [start, start + days) with start floored to 10 min.

    Raises RuntimeError when the FES2022 constants are unavailable.
    """
    start -= start % SAMPLE_STEP_SECONDS
    end = start + days * 86400
    margin = TURNING_WINDOW_SECONDS

    epochs = np.arange(start - margin, end + margin + 1, GRID_STEP_SECONDS)
    heights = predict_tide_m(epochs) * 100 + TIDE_DATUM_OFFSET_CM

    window = 2 * margin // GRID_STEP_SECONDS + 1
    rolling_max = maximum_filter1d(heights, window, mode="nearest")
    rolling_min = minimum_filter1d(heights, window, mode="nearest")

    def in_range(index: int) -> bool:
        return start <= epochs[index] < end

    def turning_points(is_turn: np.ndarray) -> List[Dict[str, int]]:
        return [
            {"t": int(epochs[i]), "h": int(round(heights[i]))}
            for i in np.flatnonzero(is_turn)
            if in_range(i)
        ]

    slack_high = []
    for run in _runs(heights >= rolling_max - SLACK_HIGH_THRESHOLD_CM):
        peak = run.start + int(np.argmax(heights[run.start:run.stop]))
        if not in_range(peak):
            continue
        slack_high.append({
            "start": int(epochs[run.start]),
            "peak": int(epochs[peak]),
            "end": int(epochs[run.stop - 1]),
            "h": int(round(heights[peak])),
        })

    sample_every = SAMPLE_STEP_SECONDS // GRID_STEP_SECONDS
    first_sample = margin // GRID_STEP_SECONDS
    samples = heights[first_sample:first_sample + days * 144 * sample_every:sample_every]

    return {
        "model": "FES2022",
        "datum_offset_cm": TIDE_DATUM_OFFSET_CM,
        "slack_threshold_cm": SLACK_HIGH_THRESHOLD_CM,
        "start": start,
        "step": SAMPLE_STEP_SECONDS,
        "heights": [int(round(h)) for h in samples],
        "highs": turning_points(heights == rolling_max),
        "lows": turning_points(heights == rolling_min),
        "slack_high": slack_high,
    }
