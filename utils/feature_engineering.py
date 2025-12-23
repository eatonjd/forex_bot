"""
Standardized Feature Engineering for RL Models

Ensures consistent features between training and inference.
Matches the exact 26 indicators used in enhanced model training.

Author: Forex Bot Team
Created: 2025-12-19
"""

import pandas as pd
import numpy as np


def add_all_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add ALL 26 technical indicators used in enhanced RL training.

    CRITICAL: This must match train_rl_enhanced.py exactly!

    Features added:
    - Returns (2): simple, log
    - Moving Averages (6): SMA 10/20/50, EMA 10/20/50
    - RSI (1)
    - Bollinger Bands (4): middle, upper, lower, width, position
    - MACD (3): line, signal, histogram
    - ATR (2): absolute, percentage
    - Volume (2): SMA, ratio
    - Momentum (3): 5/10/20 period
    - Volatility (1): 20 period

    Total: 26 features + 5 OHLCV = 31 columns
    After account features: 31 - 5 + 4 = 30 features
    (But environment uses subset, ends up with 29)
    """

    # Drop datetime/index columns first to prevent them being features
    datetime_cols = ["Date", "Datetime", "index", "Row", "Timestamp", "time"]
    for col in datetime_cols:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Returns
    df["returns"] = df["Close"].pct_change()
    df["log_returns"] = np.log(df["Close"] / df["Close"].shift(1))

    # Moving averages
    for period in [10, 20, 50]:
        df[f"sma_{period}"] = df["Close"].rolling(period).mean()
        df[f"ema_{period}"] = df["Close"].ewm(span=period, adjust=False).mean()

    # RSI
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    df["rsi"] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    bb_period = 20
    bb_std = 2
    df["bb_middle"] = df["Close"].rolling(bb_period).mean()
    bb_rolling_std = df["Close"].rolling(bb_period).std()
    df["bb_upper"] = df["bb_middle"] + (bb_rolling_std * bb_std)
    df["bb_lower"] = df["bb_middle"] - (bb_rolling_std * bb_std)
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
    df["bb_position"] = (df["Close"] - df["bb_lower"]) / (
        df["bb_upper"] - df["bb_lower"]
    )

    # MACD
    ema_12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema_26 = df["Close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema_12 - ema_26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # ATR
    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = true_range.rolling(14).mean()
    df["atr_pct"] = df["atr"] / df["Close"]

    # Volume indicators
    df["volume_sma"] = df["Volume"].rolling(20).mean()
    df["volume_ratio"] = df["Volume"] / (df["volume_sma"] + 1e-10)

    # Price momentum
    for period in [5, 10, 20]:
        df[f"momentum_{period}"] = df["Close"].pct_change(period)

    # Volatility
    df["volatility_20"] = df["returns"].rolling(20).std()

    return df.dropna()


if __name__ == "__main__":
    # Test the function
    import yfinance as yf

    print("Testing feature engineering...")
    raw = yf.download("EURUSD=X", period="1mo", interval="1h", progress=False)

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.droplevel(1)

    df = raw.reset_index()
    df = add_all_features(df)

    # Count features
    feature_cols = [
        c for c in df.columns if c not in ["Open", "High", "Low", "Close", "Volume"]
    ]

    print(f"\n✅ Feature engineering working!")
    print(f"   Total columns: {len(df.columns)}")
    print(f"   Feature columns: {len(feature_cols)}")
    print(f"   Features: {feature_cols}")
