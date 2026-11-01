import os
import time
import joblib
import keras
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

from cortex.app.engine.fetcher import fetch_data
from cortex.app.engine.model import build_model, train_model, WINDOW_SIZE

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "../../models")
os.makedirs(MODEL_DIR, exist_ok=True)

# Driven by the CURRENCIES environment variable through the schema module,
# so the trainer and the API can never disagree about what is supported.
# Set CURRENCIES=GBP,INR,USD for a quick local run; leave it unset for all 29.
from cortex.app.schemas.forecast import TRAINABLE_CURRENCIES as CURRENCIES


def run_pipeline(target_curr: str, force: bool = False):
    """
    Trains a model for EUR -> target_curr.
    Skips if the model already exists unless force=True.
    """
    pair_code = f"EUR_{target_curr}"
    ticker = f"EUR{target_curr}"

    model_path = os.path.join(MODEL_DIR, f"{pair_code}.keras")
    scaler_path = os.path.join(MODEL_DIR, f"{pair_code}_scaler.joblib")

    if not force and os.path.exists(model_path) and os.path.exists(scaler_path):
        print(f"SKIP {pair_code}: model exists. Use --force to retrain.")
        return

    print(f"\n--- Training {pair_code} ---")

    # One process trains up to 29 models in sequence, and Keras keeps
    # global backend state between builds. Clearing it before each model
    # keeps memory flat across the run, which matters under the 2G
    # container cap; without it a long run can be killed part-way with
    # exit code 137.
    keras.backend.clear_session()

    df = fetch_data(ticker, start_date="2000-01-01")
    if df is None or len(df) < 400:
        print(f"Insufficient data for {pair_code} ({len(df) if df is not None else 0} rows). Skipping.")
        return

    df = df[df["Close"] > 0.0001].copy()
    df["Return"] = df["Close"].pct_change()
    df = df[(df["Return"] > -0.15) & (df["Return"] < 0.15)]
    df.dropna(inplace=True)

    if len(df) < WINDOW_SIZE + 100:
        print(f"Data too short after cleaning ({len(df)} rows).")
        return

    data = df["Return"].values.reshape(-1, 1)
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data)

    X, y = [], []
    for i in range(WINDOW_SIZE, len(scaled_data)):
        X.append(scaled_data[i - WINDOW_SIZE : i, 0])
        y.append(scaled_data[i, 0])

    X, y = np.array(X), np.array(y)
    X = X.reshape((X.shape[0], X.shape[1], 1))

    print(f"Training {pair_code} on {len(X)} sequences...")
    model = build_model((WINDOW_SIZE, 1))
    train_model(model, X, y, epochs=50, batch_size=32, validation_split=0.15)

    model.save(model_path)
    joblib.dump(scaler, scaler_path)
    print(f"Saved: {model_path}")


if __name__ == "__main__":
    import sys

    force_retrain = "--force" in sys.argv

    print("Cortex Training Engine")
    print(f"Model directory: {os.path.abspath(MODEL_DIR)}")
    if force_retrain:
        print("FORCE MODE: All models will be retrained.\n")

    for currency in CURRENCIES:
        try:
            run_pipeline(currency, force=force_retrain)
            time.sleep(1)
        except Exception as e:
            print(f"FAILED EUR_{currency}: {e}")