#!/usr/bin/env python3
"""Derive app/gauge_calibration.json from the Aqaba tide gauge.

FES2022 at the Aqaba gauge (IOC station "aqab") is compared with a harmonic
analysis of two years of the gauge's sea level. Each main semidiurnal constituent gets an
amplitude ratio (gauge / model) and a phase shift (gauge - model, degrees of
Greenwich phase lag), which app/tides_fes2022.py applies to Dahab's constants.
Dahab and Aqaba share one co-oscillating gulf tide: in FES2022 the M2 phase
differs by 1 degree between them, so the gauge's correction carries over.

Needs the FES2022 grids and, beyond requirements.txt: utide, pandas, netCDF4.
Run from the repo root:
    python3 calibrate_from_gauge.py --start 2024-10 --end 2026-10
"""
import argparse
import json
import urllib.request
import warnings
from datetime import datetime, timezone
from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd
import utide
from scipy.interpolate import RectBivariateSpline
from scipy.ndimage import distance_transform_edt

from app.config import TIDE_MODEL_DIR

GAUGE = {'code': 'aqab', 'name': 'Aqaba', 'lat': 29.40897, 'lon': 34.97872}
# Semidiurnal only: the gauge resolves them to ~1 degree, while the small
# diurnal constituents disagree between the Aqaba and Eilat gauges.
CONSTITUENTS = ['m2', 's2', 'n2', 'k2']
FES_DIR = Path(TIDE_MODEL_DIR) / 'FES2022' / 'ocean_tide_extrapolated'
OUT_FILE = Path(__file__).parent / 'app' / 'gauge_calibration.json'
IOC_URL = ('https://www.ioc-sealevelmonitoring.org/service.php?query=data'
           '&code={code}&timestart={start}T00:00&timestop={stop}T00:00&format=json')
PYTHON_ORDINAL_1970 = 719163.0


def months(start: str, end: str):
    """Yield (first day, first day of next month) for start..end exclusive."""
    y, m = map(int, start.split('-'))
    ey, em = map(int, end.split('-'))
    while (y, m) < (ey, em):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        yield f'{y:04d}-{m:02d}-01', f'{ny:04d}-{nm:02d}-01'
        y, m = ny, nm


def gauge_series(start: str, end: str) -> pd.Series:
    """Gauge sea level in metres, 10-minute medians indexed by epoch seconds."""
    bins = {}
    for first, nxt in months(start, end):
        url = IOC_URL.format(code=GAUGE['code'], start=first, stop=nxt)
        for row in json.load(urllib.request.urlopen(url, timeout=120)):
            if row['slevel'] is None:
                continue
            t = datetime.fromisoformat(row['stime']).replace(tzinfo=timezone.utc).timestamp()
            bins.setdefault(int(t // 600) * 600 + 300, []).append(float(row['slevel']))
        print(f'  {first}: {len(bins)} bins so far', flush=True)
    series = pd.Series({t: float(np.median(v)) for t, v in sorted(bins.items())})
    # Drop spikes more than 0.5 m from the 3-hour running median.
    median = series.rolling(19, center=True, min_periods=5).median()
    return series[(series - median).abs() < 0.5]


def gauge_constants(series: pd.Series) -> dict:
    t = series.index.values / 86400.0 + PYTHON_ORDINAL_1970
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        coef = utide.solve(t, series.values, lat=GAUGE['lat'], method='robust',
                           conf_int='linear', nodal=True, trend=True,
                           verbose=False, epoch='python')
    return {n.lower(): (float(a), float(g), float(ea), float(eg))
            for n, a, g, ea, eg in zip(coef.name, coef.A, coef.g, coef.A_ci, coef.g_ci)}


def fes_constants(constituent: str) -> tuple:
    """FES2022 amplitude (m) and phase (deg) spline-interpolated at the gauge."""
    data = netCDF4.Dataset(FES_DIR / f'{constituent}_fes2022.nc')
    lat, lon = data['lat'][:], data['lon'][:]
    i = np.flatnonzero((lat > GAUGE['lat'] - 1) & (lat < GAUGE['lat'] + 1))
    j = np.flatnonzero((lon > GAUGE['lon'] - 1) & (lon < GAUGE['lon'] + 1))
    window = (slice(i[0], i[-1] + 1), slice(j[0], j[-1] + 1))
    amp = np.ma.filled(data['amplitude'][window].astype(float), np.nan)
    phase = np.ma.filled(data['phase'][window].astype(float), np.nan)
    z = amp * np.exp(-1j * np.deg2rad(phase))
    land = ~np.isfinite(z)
    if land.any():  # fill land cells from the nearest ocean cell
        z = z[tuple(distance_transform_edt(land, return_distances=False, return_indices=True))]
    re = RectBivariateSpline(lat[i], lon[j], z.real)(GAUGE['lat'], GAUGE['lon'])[0, 0]
    im = RectBivariateSpline(lat[i], lon[j], z.imag)(GAUGE['lat'], GAUGE['lon'])[0, 0]
    value = complex(re, im)
    return abs(value) / 100.0, float(np.rad2deg(-np.angle(value)) % 360)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--start', required=True, help='first month, YYYY-MM')
    parser.add_argument('--end', required=True, help='end month (exclusive), YYYY-MM')
    args = parser.parse_args()

    print(f"Fetching {GAUGE['name']} gauge {args.start} to {args.end}")
    series = gauge_series(args.start, args.end)
    observed = gauge_constants(series)

    corrections = {}
    print('const  gauge amp  FES amp  ratio   gauge g  FES g   shift')
    for c in CONSTITUENTS:
        a_obs, g_obs, a_ci, g_ci = observed[c]
        a_fes, g_fes = fes_constants(c)
        shift = (g_obs - g_fes + 180) % 360 - 180
        corrections[c] = {
            'amplitude_ratio': round(a_obs / a_fes, 4),
            'phase_shift_deg': round(shift, 2),
            'gauge_amplitude_m': round(a_obs, 4),
            'gauge_amplitude_ci_m': round(a_ci, 4),
            'gauge_phase_deg': round(g_obs, 2),
            'gauge_phase_ci_deg': round(g_ci, 2),
            'fes_amplitude_m': round(a_fes, 4),
            'fes_phase_deg': round(g_fes, 2),
        }
        print(f'{c:5s} {a_obs*100:9.2f} {a_fes*100:8.2f} {a_obs/a_fes:6.3f} '
              f'{g_obs:8.1f} {g_fes:6.1f} {shift:+7.1f}')

    OUT_FILE.write_text(json.dumps({
        'gauge': GAUGE,
        'source': 'IOC Sea Level Station Monitoring Facility',
        'period': {'start': args.start, 'end': args.end,
                   'samples': int(len(series)),
                   'days': round((series.index[-1] - series.index[0]) / 86400, 1)},
        'method': 'UTide robust harmonic analysis vs FES2022 spline-interpolated at the gauge',
        'constituents': corrections,
    }, indent=2) + '\n')
    print(f'Wrote {OUT_FILE}')


if __name__ == '__main__':
    main()
