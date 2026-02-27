#!/usr/bin/env python3
"""Extract FES2022 harmonic constants for Dahab and cache them.

This only needs to run once. The extracted constants are saved to a small
JSON file that can be loaded quickly for tide predictions.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, '/var/www/dahab-api')

from app.config import LATITUDE, LONGITUDE, TIDE_MODEL_DIR

# FES2022 constituents
CONSTITUENTS = [
    '2n2', 'eps2', 'j1', 'k1', 'k2', 'l2', 'lambda2', 'm2', 'm3', 'm4',
    'm6', 'm8', 'mf', 'mks2', 'mm', 'mn4', 'ms4', 'msf', 'msqm', 'mtm',
    'mu2', 'n2', 'n4', 'nu2', 'o1', 'p1', 'q1', 'r2', 's1', 's2', 's4',
    'sa', 'ssa', 't2'
]

MODEL_DIR = Path(TIDE_MODEL_DIR) / 'FES2022' / 'ocean_tide_extrapolated'
CACHE_FILE = Path(TIDE_MODEL_DIR) / 'FES2022' / 'dahab_constants.json'


def extract_constants():
    """Extract amplitude and phase for each constituent at Dahab."""
    import pyTMD.io.FES

    print(f"Extracting FES2022 constants for Dahab ({LATITUDE}, {LONGITUDE})")
    print(f"Model directory: {MODEL_DIR}")
    print()

    # Single point arrays
    lons = np.array([LONGITUDE])
    lats = np.array([LATITUDE])

    results = {
        'latitude': LATITUDE,
        'longitude': LONGITUDE,
        'constituents': [],
        'amplitude': [],  # in meters
        'phase': [],      # in degrees
    }

    for i, c in enumerate(CONSTITUENTS):
        model_file = MODEL_DIR / f'{c}_fes2022.nc'
        if not model_file.exists():
            print(f"  [{i+1:2d}/{len(CONSTITUENTS)}] {c}: MISSING")
            continue

        print(f"  [{i+1:2d}/{len(CONSTITUENTS)}] {c}...", end=' ', flush=True)

        try:
            amp, ph = pyTMD.io.FES.extract_constants(
                lons, lats,
                type='z',
                version='FES2014',  # FES2022 uses same format
                model_files=[model_file],
                model_directory=MODEL_DIR,
                scale=1.0/100.0,  # cm to m
                compressed=False,
                method='spline',
                extrapolate=True,
                cutoff=10.0
            )

            # Get the single values
            a = float(amp[0, 0]) if not np.ma.is_masked(amp[0, 0]) else 0.0
            p = float(ph[0, 0]) if not np.ma.is_masked(ph[0, 0]) else 0.0

            results['constituents'].append(c)
            results['amplitude'].append(a)
            results['phase'].append(p)

            print(f"amp={a:.4f}m, phase={p:.1f}°")

        except Exception as e:
            print(f"ERROR: {e}")

    # Save to cache file
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump(results, f, indent=2)

    print()
    print(f"Extracted {len(results['constituents'])} constituents")
    print(f"Saved to: {CACHE_FILE}")

    # Show major constituents
    print()
    print("Major constituents:")
    for c, a, p in zip(results['constituents'], results['amplitude'], results['phase']):
        if c in ['m2', 's2', 'n2', 'k1', 'o1', 'k2', 'p1', 'q1']:
            print(f"  {c}: amp={a:.4f}m, phase={p:.1f}°")


if __name__ == '__main__':
    extract_constants()
