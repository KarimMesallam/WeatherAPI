"""FES2022 tide computation module.

Uses pre-extracted harmonic constants from dahab_constants.json for fast
tide predictions. The constants are extracted once using extract_fes2022_constants.py.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

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


def compute_tides_fes2022() -> Optional[List[int]]:
    """Compute hourly tide heights using FES2022 cached constants.

    Returns list of tide heights in centimeters, or None if computation fails.
    Uses pre-extracted harmonic constants for fast computation.
    """
    try:
        import pyTMD.arguments
        import pyTMD.predict

        # Load cached constants
        constants = _load_constants()
        if constants is None:
            return None

        constituents = constants['constituents']
        amp = np.array(constants['amplitude'])  # meters
        ph = np.array(constants['phase'])       # degrees

        # Time setup - pyTMD.predict.drift uses days since 1992-01-01
        now = datetime.utcnow()
        epoch_1992 = datetime(1992, 1, 1, 0, 0, 0)
        base_days = (now - epoch_1992).total_seconds() / 86400.0
        base_days = (base_days // (1/24)) * (1/24)  # Round to hour

        n = FORECAST_HOURS

        # Create time array (days since 1992-01-01)
        t = np.array([base_days + i / 24.0 for i in range(n)])

        # Convert amplitude/phase to complex harmonic constants
        # hc = amp * exp(i * phase_radians)
        # Shape must be (npts, nconstituents) - we have n time points, 1 spatial point
        # pyTMD expects masked arrays
        ph_rad = np.deg2rad(ph)
        hc_single = amp * np.exp(1j * ph_rad)  # (nconstituents,)
        hc = np.ma.array(np.tile(hc_single, (n, 1)))  # (n, nconstituents) as masked array
        hc.mask = np.zeros_like(hc, dtype=bool)  # No masked values

        # Predict tides using harmonic synthesis
        tide = pyTMD.predict.drift(
            t,
            hc,
            constituents,
            deltat=0.0,
            corrections='FES'
        )

        # Convert to cm and apply datum offset
        tide_cm = [int(round(float(t) * 100)) + TIDE_DATUM_OFFSET_CM for t in tide]

        logger.info(
            "FES2022: Computed %d tide values (range: %d to %d cm, offset: +%d cm)",
            len(tide_cm),
            min(tide_cm),
            max(tide_cm),
            TIDE_DATUM_OFFSET_CM,
        )
        return tide_cm

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
