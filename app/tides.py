import logging
from datetime import datetime
from typing import List, Optional

import numpy as np

from app.config import (
    FORECAST_HOURS,
    LATITUDE,
    LONGITUDE,
    TIDE_DATUM_OFFSET_CM,
    TIDE_MODEL_DIR,
    TIDE_MODEL_NAME,
)

logger = logging.getLogger(__name__)


def compute_tides() -> Optional[List[int]]:
    """Compute hourly tide heights using the configured model.

    Uses TIDE_MODEL_NAME from config to select between:
    - GOT4.10: Default, lower resolution but works
    - FES2022: Higher resolution (1/30°), better for Gulf of Aqaba

    Returns list of tide heights in centimeters, or None if computation fails.
    """
    if TIDE_MODEL_NAME == "FES2022":
        from app.tides_fes2022 import compute_tides_fes2022
        return compute_tides_fes2022()
    else:
        return _compute_tides_got410()


def _compute_tides_got410() -> Optional[List[int]]:
    """Compute hourly tide heights using GOT4.10 model.

    Returns list of tide heights in centimeters, or None if computation fails.
    Uses pyTMD with the GOT4.10 model and extrapolation (Red Sea is narrow,
    the model grid may not cover Dahab directly).
    """
    try:
        import pyTMD

        now = datetime.utcnow()
        epoch = datetime(2000, 1, 1, 0, 0, 0)
        base_seconds = (now - epoch).total_seconds()
        # Round down to the current hour
        base_seconds = (base_seconds // 3600) * 3600

        n = FORECAST_HOURS
        delta_times = np.array(
            [base_seconds + i * 3600 for i in range(n)]
        )
        lons = np.full(n, LONGITUDE)
        lats = np.full(n, LATITUDE)

        tide = pyTMD.compute_tide_corrections(
            lons,
            lats,
            delta_times,
            DIRECTORY=TIDE_MODEL_DIR,
            MODEL="GOT4.10",  # Hardcoded for this function
            EPOCH=(2000, 1, 1, 0, 0, 0),
            TYPE="drift",
            TIME="UTC",
            EPSG=4326,
            METHOD="spline",
            EXTRAPOLATE=True,
            CUTOFF=np.inf,
        )

        # Convert to cm and apply datum offset (MSL → chart datum)
        tide_cm = [int(round(float(t) * 100)) + TIDE_DATUM_OFFSET_CM for t in tide]
        logger.info(
            "Computed %d tide values (range: %d to %d cm, offset: +%d cm)",
            len(tide_cm),
            min(tide_cm),
            max(tide_cm),
            TIDE_DATUM_OFFSET_CM,
        )
        return tide_cm

    except Exception as exc:
        logger.error("Tide computation failed: %s", exc, exc_info=True)
        return None
