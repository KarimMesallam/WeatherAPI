"""FES2022 tide computation module.

Uses pre-extracted harmonic constants from dahab_constants.json for fast
tide predictions. The constants are extracted once using extract_fes2022_constants.py.
"""
import calendar
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from app.config import (
    FORECAST_HOURS,
    TIDE_DATUM_OFFSET_CM,
    TIDE_MODEL_DIR,
)

logger = logging.getLogger(__name__)

CACHE_FILE = Path(TIDE_MODEL_DIR) / 'FES2022' / 'dahab_constants.json'

# Cached constants (loaded on first use)
_cached_constants = None


def _load_constants():
    """Load pre-extracted harmonic constants from cache file."""
    global _cached_constants
    if _cached_constants is not None:
        return _cached_constants

    if not CACHE_FILE.exists():
        logger.error("FES2022 constants cache not found: %s", CACHE_FILE)
        logger.error("Run: python3 extract_fes2022_constants.py")
        return None

    with open(CACHE_FILE) as f:
        _cached_constants = json.load(f)

    logger.info(
        "Loaded FES2022 constants: %d constituents for (%.4f, %.4f)",
        len(_cached_constants['constituents']),
        _cached_constants['latitude'],
        _cached_constants['longitude']
    )
    return _cached_constants


# pyTMD.predict.drift measures time in days since this epoch (1992-01-01 UTC)
PYTMD_EPOCH_UNIX = 694224000


def predict_tide_m(epochs: np.ndarray) -> np.ndarray:
    """Predict tide heights in metres relative to MSL at Unix epoch seconds.

    Raises RuntimeError when the FES2022 constants file is missing.
    """
    import pyTMD.predict

    constants = _load_constants()
    if constants is None:
        raise RuntimeError("FES2022 constants not available")

    constituents = constants['constituents']
    amp = np.array(constants['amplitude'])  # meters
    ph = np.array(constants['phase'])       # degrees

    t = (np.asarray(epochs, dtype=float) - PYTMD_EPOCH_UNIX) / 86400.0
    n = len(t)

    # Convert amplitude/phase to complex harmonic constants
    # Must use -1j to match pyTMD's internal convention (see compute_tide_corrections)
    # Shape must be (npts, nconstituents) - we have n time points, 1 spatial point
    # pyTMD expects masked arrays
    ph_rad = np.deg2rad(ph)
    hc_single = amp * np.exp(-1j * ph_rad)  # (nconstituents,)
    hc = np.ma.array(np.tile(hc_single, (n, 1)))  # (n, nconstituents) as masked array
    hc.mask = np.zeros_like(hc, dtype=bool)  # No masked values

    return np.asarray(
        pyTMD.predict.drift(t, hc, constituents, deltat=0.0, corrections='FES')
    )


def compute_tides_fes2022() -> Optional[Tuple[List[int], int]]:
    """Compute hourly tide heights using FES2022 cached constants.

    Returns (list of tide heights in centimeters, epoch seconds of index 0),
    or None if computation fails. Index 0 is the UTC hour the computation
    ran in, so consumers know the array's time base.
    Uses pre-extracted harmonic constants for fast computation.
    """
    try:
        # Index 0 is the current UTC hour, and base_ts reports it.
        now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        base_ts = calendar.timegm(now.timetuple())
        epochs = base_ts + 3600 * np.arange(FORECAST_HOURS)

        tide = predict_tide_m(epochs)

        # Convert to cm and apply datum offset
        tide_cm = [int(round(float(t) * 100)) + TIDE_DATUM_OFFSET_CM for t in tide]

        logger.info(
            "FES2022: Computed %d tide values (range: %d to %d cm, offset: +%d cm)",
            len(tide_cm),
            min(tide_cm),
            max(tide_cm),
            TIDE_DATUM_OFFSET_CM,
        )
        return tide_cm, base_ts

    except Exception as exc:
        logger.error("FES2022 tide computation failed: %s", exc, exc_info=True)
        return None


def verify_fes2022_installation() -> dict:
    """Check if FES2022 is properly installed and return status."""
    result = {
        'cache_file': str(CACHE_FILE),
        'cache_exists': CACHE_FILE.exists(),
        'constituents_count': 0,
        'ready': False,
    }

    if CACHE_FILE.exists():
        try:
            constants = _load_constants()
            if constants:
                result['constituents_count'] = len(constants['constituents'])
                result['latitude'] = constants['latitude']
                result['longitude'] = constants['longitude']
                result['ready'] = result['constituents_count'] >= 8  # At least major constituents
        except Exception as e:
            result['error'] = str(e)

    return result
