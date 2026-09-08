import pandas as pd
import numpy as np


def calculate_indicators(df):

    if len(df) < 210:
        return None

    df = df.copy()

    close = df["close"]
    volume = df["volume"]


    # =========================
    # EMA 200
    # =========================

    ema200 = close.ewm(
        span=200,
        adjust=False
    ).mean()


    # =========================
    # RSI 14
    # =========================

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(
        window=14
    ).mean()

    avg_loss = loss.rolling(
        window=14
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    rsi = 100 - (
        100 / (1 + rs)
    )

    current_rsi = rsi.iloc[-1]

    if pd.isna(current_rsi):
        current_rsi = 50


    # =========================
    # Volume Ratio
    # =========================

    avg_volume = volume.iloc[-21:-1].mean()

    if avg_volume <= 0 or pd.isna(avg_volume):
        volume_ratio = 0
    else:
        volume_ratio = (
            volume.iloc[-1] /
            avg_volume
        )


    # =========================
    # Price Momentum
    # =========================

    price_10 = close.iloc[-10]

    if price_10 == 0:
        momentum = 0
    else:
        momentum = (
            (close.iloc[-1] / price_10) - 1
        ) * 100


    # =========================
    # Accumulation Proxy
    # =========================

    price_change_20 = (
        (close.iloc[-1] /
         close.iloc[-20]) - 1
    ) * 100


    return {
        "price": float(close.iloc[-1]),

        "rsi": float(current_rsi),

        "ema200": float(
            ema200.iloc[-1]
        ),

        "above_ema200": bool(
            close.iloc[-1] >
            ema200.iloc[-1]
        ),

        "volume_ratio": float(
            volume_ratio
        ),

        "momentum": float(
            momentum
        ),

        "price_change_20": float(
            price_change_20
        ),

        "current_volume": float(
            volume.iloc[-1]
        ),

        "average_volume": float(
            avg_volume
        )
    }
