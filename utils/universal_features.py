import pandas as pd
import numpy as np


def add_universal_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add price-invariant features for better generalization across assets.

    This converts raw price data into ratios, percentages, and boolean flags
    that allow models to learn market structure independent of absolute price.

    Features added:
    - Normalized prices relative to MAs (SMA 20, 50, 200)
    - Volatility regimes (boolean)
    - Trend regimes (boolean)
    - Volume relative to average
    - Bollinger Band position (normalized)
    """
    df = df.copy()

    # 1. Price vs Moving Averages (Ratios)
    # Instead of raw price, how far is price from the MA in %?
    for period in [20, 50, 200]:
        col_name = f"sma_{period}"
        if col_name not in df.columns:
            df[col_name] = df["Close"].rolling(window=period).mean()

        # Log-ratio helps with symmetry: ln(price/ma)
        # 0 = at MA, >0 = above, <0 = below
        df[f"close_vs_sma_{period}_pct"] = np.log(df["Close"] / (df[col_name] + 1e-8))

    # 2. Normalized Volume (Invariant volume)
    # Volume relative to 20-day average
    vol_ma = df["Volume"].rolling(window=20).mean()
    df["volume_rel"] = df["Volume"] / (vol_ma + 1e-8)

    # 3. Bollinger Band Position (Standardized)
    # 0 = at SMA, 1 = at Upper Band, -1 = at Lower Band
    # This is more robust than raw width
    period = 20
    sma = df["Close"].rolling(window=period).mean()
    std = df["Close"].rolling(window=period).std()

    # Z-score of price relative to Bollinger Bands
    df["bb_zscore"] = (df["Close"] - sma) / (std + 1e-8)

    # 4. Volatility Regimes (Boolean Flags)
    # ATR relative to price
    high = df["High"]
    low = df["Low"]
    close_prev = df["Close"].shift(1)

    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=14).mean()

    # Normalized ATR (Volatility %)
    df["natr"] = (atr / df["Close"]) * 100

    # Regime Flags (One-Hot / Boolean features for NN)
    # Low Volatility < 1%, High > 2.5% (approximate for daily)
    # Using rolling quantile for broader usage?
    # Let's stick to adaptive thresholds or fixed heuristics.

    # Adaptive: High Volatility is above 80th percentile of last 100 days
    atr_rolling_80 = df["natr"].rolling(window=100).quantile(0.8)
    atr_rolling_20 = df["natr"].rolling(window=100).quantile(0.2)

    df["regime_vol_high"] = (df["natr"] > atr_rolling_80).astype(int)
    df["regime_vol_low"] = (df["natr"] < atr_rolling_20).astype(int)

    # 5. Trend Regimes (Boolean)
    # Uptrend: Price > SMA50 > SMA200
    sma_50 = df["sma_50"]
    sma_200 = df["sma_200"]

    df["trend_uptrend"] = ((df["Close"] > sma_50) & (sma_50 > sma_200)).astype(int)
    df["trend_downtrend"] = ((df["Close"] < sma_50) & (sma_50 < sma_200)).astype(int)

    # 6. Regime Uncertainty (High Vol + No Clear Trend)
    # High vol but moving averages are criss-crossing or flat?
    # Simple proxy: High Vol and NOT (Uptrend or Downtrend)
    df["regime_uncertainty"] = (
        (df["regime_vol_high"] == 1)
        & (df["trend_uptrend"] == 0)
        & (df["trend_downtrend"] == 0)
    ).astype(int)

    return df


def get_universal_feature_names(df: pd.DataFrame) -> list:
    """Return list of universal feature columns."""
    universal_cols = [
        "close_vs_sma_20_pct",
        "close_vs_sma_50_pct",
        "close_vs_sma_200_pct",
        "volume_rel",
        "bb_zscore",
        "natr",
        "regime_vol_high",
        "regime_vol_low",
        "trend_uptrend",
        "trend_downtrend",
        "regime_uncertainty",
    ]
    return [col for col in universal_cols if col in df.columns]
