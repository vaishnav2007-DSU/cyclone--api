"""
Real-time satellite data fetcher — Himawari-9 (JMA), via NOAA's free public
AWS S3 mirror. No API key required; the bucket is public.

Bucket: s3://noaa-himawari9/AHI-L1b-FLDK/  (Himawari-8 used the same layout
        under s3://noaa-himawari8/ before it was retired in Dec 2022)

Full-disk scans happen every 10 minutes (:00, :10, :20 ...). Each band is
split into 10 latitude-band "segments" (S01..S10) stored as bz2-compressed
HSD files. There's usually a 10-20 min processing delay before a scan
appears in the bucket, so we walk backward in time until we find one.
"""

import datetime as dt
import io
import bz2
import tempfile
import os

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from satpy import Scene

BUCKET = "noaa-himawari9"

# Band 13 = IR window channel (~10.4 micron) — standard proxy for cloud-top
# temperature, which is what intensity estimation (Dvorak-style) is based on.
BAND = "B13"
RESOLUTION = "R20"  # 2km, matches Band 13's native resolution
NUM_SEGMENTS = 10

s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))


def _candidate_timestamps(lookback_minutes=60):
    """Yield 10-minute-aligned timestamps, most recent first, going back
    `lookback_minutes` to account for processing delay."""
    now = dt.datetime.utcnow()
    aligned = now - dt.timedelta(minutes=now.minute % 10, seconds=now.second, microseconds=now.microsecond)
    for i in range(lookback_minutes // 10 + 1):
        yield aligned - dt.timedelta(minutes=10 * i)


def _segment_key(ts, segment):
    date_prefix = ts.strftime("%Y/%m/%d")
    hhmm = ts.strftime("%H%M")
    fname = f"HS_H09_{ts.strftime('%Y%m%d')}_{hhmm}_{BAND}_FLDK_{RESOLUTION}_S{segment:02d}10.DAT.bz2"
    return f"AHI-L1b-FLDK/{date_prefix}/{hhmm}/{fname}"


def _object_exists(key):
    try:
        s3.head_object(Bucket=BUCKET, Key=key)
        return True
    except Exception:
        return False


def find_latest_scan_time(lookback_minutes=60):
    """Find the most recent full-disk scan that's actually available in the
    bucket (checks segment 1 as a proxy for the whole scan existing)."""
    for ts in _candidate_timestamps(lookback_minutes):
        probe_key = _segment_key(ts, 1)
        if _object_exists(probe_key):
            return ts
    return None


def fetch_latest_satellite_data(region_bounds, lookback_minutes=60, segments=None):
    """
    Fetch the latest available Himawari-9 Band 13 (IR) full-disk data,
    cropped to `region_bounds`, and return it as a satpy Scene.

    region_bounds: (lon_min, lat_min, lon_max, lat_max)
        e.g. Bay of Bengal ≈ (78, 5, 100, 25)

    segments: optionally restrict which of the 10 latitude-band segments to
    download (1-10, north to south) if you already know which ones overlap
    your region — saves bandwidth. Defaults to all 10 (safe but heavier).
    """
    ts = find_latest_scan_time(lookback_minutes)
    if ts is None:
        raise RuntimeError(
            f"No Himawari-9 scan found in the last {lookback_minutes} minutes. "
            "The bucket may be delayed, or the naming scheme may have changed — "
            "check https://noaa-himawari9.s3.amazonaws.com/index.html"
        )

    segments_to_fetch = segments or range(1, NUM_SEGMENTS + 1)

    with tempfile.TemporaryDirectory() as tmpdir:
        local_paths = []
        for seg in segments_to_fetch:
            key = _segment_key(ts, seg)
            local_bz2 = os.path.join(tmpdir, os.path.basename(key))
            local_dat = local_bz2[:-4]  # strip .bz2
            s3.download_file(BUCKET, key, local_bz2)
            with bz2.open(local_bz2, "rb") as fin, open(local_dat, "wb") as fout:
                fout.write(fin.read())
            local_paths.append(local_dat)

        scn = Scene(reader="ahi_hsd", filenames=local_paths)
        scn.load(["B13"])
        cropped = scn.crop(ll_bbox=region_bounds)

        return {
            "scan_time": ts.isoformat() + "Z",
            "brightness_temp": cropped["B13"].values,  # numpy array, Kelvin
        }
