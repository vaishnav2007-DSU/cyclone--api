# Cyclone Prediction API — Real-Time Himawari + Baseline Estimator

## What this actually is (read this first)
This is a working MVP, not a research-grade forecaster:
- **Real, live data**: fetches the latest Himawari-9 IR satellite scan
  (free, no API key) for the North Indian Ocean basin.
- **Real feature extraction**: cloud-top brightness temperature — the actual
  signal used in operational intensity estimation.
- **A baseline heuristic**, not a trained model: `/predict` currently
  returns an estimate from simple, documented thresholds (see `model.py`).
  It is not calibrated against historical storms and should not be trusted
  for real decisions. There's a clean slot (`MODEL` in `model.py`) to drop
  in a real trained model once you have one — see "Training a real model" below.

**I could not test the satellite fetch from my side** — my sandbox's network
is locked to package registries, not AWS. The code follows Himawari's
long-standing public HSD format, but run the local test below before you
deploy, in case anything about the bucket has changed.

## Files
- `app.py` — Flask app: `/predict` (cached, auto-refreshes every 20 min) and `/` (health check)
- `satellite.py` — fetches + decodes the latest Himawari-9 IR scan from AWS (no key needed)
- `model.py` — baseline heuristic + the slot for your real trained model
- `requirements.txt`, `Procfile` — deployment config

## 1. Test locally first
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -c "
from satellite import fetch_latest_satellite_data
data = fetch_latest_satellite_data((60, 0, 100, 25))
print(data['scan_time'], data['brightness_temp'].shape)
"
```
If this errors, check `https://noaa-himawari9.s3.amazonaws.com/index.html`
in a browser to see the current folder structure and adjust the key format
in `satellite.py`'s `_segment_key()` function accordingly.

Then run the full app:
```bash
python app.py
# in another terminal:
curl http://localhost:5000/predict
curl "http://localhost:5000/predict?fresh=true&lon_min=80&lat_min=5&lon_max=95&lat_max=20"
```

## 2. Deploy (Render, recommended)
1. Push this folder to a GitHub repo.
2. [render.com](https://render.com) → New → Web Service → connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app --timeout 120`
   (longer timeout — satpy loading + S3 download takes a bit)
5. **Instance size matters here**: `satpy` + downloading/decoding 10 segments
   of full-disk IR data is memory-hungry (expect 500MB-1GB+ RAM during a
   fetch). Render's free 512MB tier will likely struggle — use at least
   their Starter paid tier, or trim `segments=[...]` in `satellite.py` to
   only the 2-3 segments that cover your bounding box latitude band once
   you've confirmed which ones those are from local testing.
6. You'll get a URL like `https://your-app.onrender.com/predict`.

### Alternative: Hugging Face Spaces (Docker SDK)
Better if you want more free RAM/compute headroom — geoscience/ML workloads
like this are common there. Same files work; add a `Dockerfile` that installs
`requirements.txt` and runs `gunicorn app:app`.

### Why not Netlify
Netlify only runs static sites / short-lived serverless functions. This app
needs a persistent background thread (the auto-refresh loop) and heavy
geospatial libraries — that doesn't fit Netlify's model.

## 3. Training a real model (next step, when you're ready)
The baseline heuristic in `model.py` is not a substitute for a trained
model. To build one properly:
1. Get historical best-track data for the North Indian Ocean basin from
   **IBTrACS** (NOAA, free, global coverage including Bay of Bengal/Arabian
   Sea): https://www.ncei.noaa.gov/products/international-best-track-archive
   — gives you storm time, position, and observed max wind for every past
   cyclone.
2. For each historical storm timestamp, pull the matching Himawari (or
   older MTSAT/pre-2015 alternative) scan and extract the same features
   `model.py` computes (min/mean/std cloud-top temp).
3. Train a regression model (start simple — gradient boosting or even
   linear regression — before reaching for deep learning) predicting
   observed max wind from those features.
4. Export it (`joblib.dump(model, "model.pkl")`), load it in `model.py`'s
   `MODEL` variable, and `predict()` will automatically use it instead of
   the heuristic.

This step is genuinely substantial (data wrangling across two sources,
temporal alignment, validation) — happy to help you build it out piece by
piece whenever you're ready to start.
