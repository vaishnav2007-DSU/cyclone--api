import os
import threading
import time
import traceback

from flask import Flask, jsonify, request

from satellite import fetch_latest_satellite_data
from model import predict

app = Flask(__name__)

# Default region: Bay of Bengal + adjacent Arabian Sea (North Indian Ocean
# cyclone basin). Override per-request via query params, see /predict below.
DEFAULT_REGION = (60.0, 0.0, 100.0, 25.0)  # lon_min, lat_min, lon_max, lat_max

REFRESH_SECONDS = int(os.environ.get("REFRESH_SECONDS", 20 * 60))  # every 20 min

_cache_lock = threading.Lock()
_cache = {"result": None, "error": None, "updated_at": None}


def _refresh_loop():
    while True:
        try:
            data = fetch_latest_satellite_data(DEFAULT_REGION)
            result = predict(data["brightness_temp"])
            result["scan_time"] = data["scan_time"]
            with _cache_lock:
                _cache["result"] = result
                _cache["error"] = None
                _cache["updated_at"] = time.time()
        except Exception as e:
            with _cache_lock:
                _cache["error"] = str(e)
                _cache["updated_at"] = time.time()
            traceback.print_exc()
        time.sleep(REFRESH_SECONDS)


@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "Cyclone prediction API is running"})


@app.route("/predict", methods=["GET"])
def predict_cyclone():
    """
    Returns the latest cached prediction (refreshed automatically every
    REFRESH_SECONDS in the background — fetching + decoding satellite data
    per-request would be too slow/heavy for a live HTTP call).

    Optional query params to fetch a fresh reading on-demand instead of the
    cache (slower — expect 10-30s+):
        ?fresh=true&lon_min=..&lat_min=..&lon_max=..&lat_max=..
    """
    if request.args.get("fresh") == "true":
        bounds = (
            float(request.args.get("lon_min", DEFAULT_REGION[0])),
            float(request.args.get("lat_min", DEFAULT_REGION[1])),
            float(request.args.get("lon_max", DEFAULT_REGION[2])),
            float(request.args.get("lat_max", DEFAULT_REGION[3])),
        )
        try:
            data = fetch_latest_satellite_data(bounds)
            result = predict(data["brightness_temp"])
            result["scan_time"] = data["scan_time"]
            return jsonify({"status": "success", **result})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    with _cache_lock:
        if _cache["result"] is None and _cache["error"] is None:
            return jsonify({"status": "warming_up", "message": "First fetch in progress, try again shortly"}), 202
        if _cache["error"] is not None and _cache["result"] is None:
            return jsonify({"status": "error", "message": _cache["error"]}), 500
        return jsonify({"status": "success", "cached": True, "updated_at": _cache["updated_at"], **_cache["result"]})


# Kick off the background refresh loop once, at import time (works under
# gunicorn too, not just `python app.py`).
_bg_thread = threading.Thread(target=_refresh_loop, daemon=True)
_bg_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
