"""
Cyclone intensity estimation.

Two things live here:

1. `baseline_estimate()` — a simple, transparent heuristic based on cloud-top
   brightness temperature (colder cloud tops = deeper convection = generally
   stronger system). This is inspired by the logic behind the Dvorak
   technique, but it is NOT the real Dvorak technique (which also uses eye
   pattern, banding, and shear structure — real forecasters use trained
   judgment plus tools like ADT). Treat this as a rough, explainable
   placeholder, not a forecast-grade estimate.

2. `MODEL` — the slot for your real trained model, once you have one. See
   README.md "Training a real model" section for how to get there using
   IBTrACS historical data.
"""

import numpy as np

MODEL = None  # <-- load your real trained model here once you have one


def baseline_estimate(brightness_temp_kelvin: np.ndarray) -> dict:
    """
    Very rough intensity proxy from IR cloud-top temperature.
    Colder min brightness temp -> deeper overshooting convection -> higher
    estimated intensity. Thresholds below are illustrative, loosely anchored
    to typical tropical cyclone cloud-top temps, NOT an official standard.
    """
    valid = brightness_temp_kelvin[~np.isnan(brightness_temp_kelvin)]
    if valid.size == 0:
        raise ValueError("No valid pixels in region — check region_bounds overlaps the scan")

    min_temp_k = float(np.min(valid))
    mean_temp_k = float(np.mean(valid))
    min_temp_c = min_temp_k - 273.15

    # Illustrative banding — replace with a real model as soon as you can.
    if min_temp_c > -60:
        category = "No significant convection / disturbance"
        est_wind_kmh = 0
    elif min_temp_c > -75:
        category = "Deep convection present (depression-strength range)"
        est_wind_kmh = 55
    elif min_temp_c > -85:
        category = "Strong convection (cyclonic storm range)"
        est_wind_kmh = 90
    else:
        category = "Very cold overshooting tops (severe cyclonic storm+ range)"
        est_wind_kmh = 140

    return {
        "min_cloud_top_temp_c": round(min_temp_c, 1),
        "mean_cloud_top_temp_c": round(mean_temp_k - 273.15, 1),
        "category": category,
        "estimated_max_wind_kmh": est_wind_kmh,
        "method": "baseline_heuristic_v0 (not a trained model)",
    }


def predict(brightness_temp_kelvin: np.ndarray) -> dict:
    if MODEL is not None:
        # Swap in real feature engineering + MODEL.predict() here once
        # you've trained something on IBTrACS + historical imagery.
        features = _extract_features(brightness_temp_kelvin)
        pred = MODEL.predict([features])
        return {"estimated_max_wind_kmh": float(pred[0]), "method": "trained_model"}
    return baseline_estimate(brightness_temp_kelvin)


def _extract_features(brightness_temp_kelvin: np.ndarray) -> list:
    valid = brightness_temp_kelvin[~np.isnan(brightness_temp_kelvin)]
    return [
        float(np.min(valid)),
        float(np.mean(valid)),
        float(np.std(valid)),
        float(np.percentile(valid, 5)),
    ]
