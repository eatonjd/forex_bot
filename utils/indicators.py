"""
Technical Indicator calculations for the Trading Bot.

Includes RSI, MACD, Bollinger Bands, and other common indicators.
"""

import pandas as pd
import numpy as np


def add_technical_indicators(
    df: pd.DataFrame,
    include_regime_features: bool = False,  # Set True for new models
) -> pd.DataFrame:
    """
    Add all technical indicators to the DataFrame.

    Args:
        df: DataFrame with OHLCV data
        include_regime_features: If True, add composite regime and difficulty scores.
                                 Set to False for backward compatibility with older models.

    Returns:
        DataFrame with additional indicator columns
    """
    df = df.copy()

    # Price-based features
    df = add_price_features(df)

    # Momentum indicators
    df = add_rsi(df)
    df = add_macd(df)
    df = add_momentum_features(df)

    # Volatility indicators
    df = add_bollinger_bands(df)
    df = add_atr(df)

    # Volume indicators
    df = add_volume_features(df)

    # Moving averages
    df = add_moving_averages(df)

    # Regime features (optional - for new models only)
    if include_regime_features:
        df = add_regime_features(df)

    return df


def add_price_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add price-based features like returns and normalized prices."""
    df = df.copy()

    # Returns over different windows
    df["return_1d"] = df["Close"].pct_change(1)
    df["return_5d"] = df["Close"].pct_change(5)
    df["return_20d"] = df["Close"].pct_change(20)

    # Normalized price (relative to 20-day moving average)
    df["price_norm"] = df["Close"] / df["Close"].rolling(window=20).mean() - 1

    # Daily range
    df["daily_range"] = (df["High"] - df["Low"]) / df["Close"]

    # Gap (open vs previous close)
    df["gap"] = df["Open"] / df["Close"].shift(1) - 1

    # Universal Price Features (Scale Invariant)
    # 1. Price position within daily range (0-1)
    # 0 = Close at Low, 1 = Close at High
    high_low_range = df["High"] - df["Low"]
    df["price_position"] = np.where(
        high_low_range > 0, (df["Close"] - df["Low"]) / high_low_range, 0.5
    )

    # 2. Body to Range Ratio (Candle strength)
    # Size of body relative to total wick length
    body_size = abs(df["Close"] - df["Open"])
    df["body_to_range"] = np.where(high_low_range > 0, body_size / high_low_range, 0)

    return df


def add_momentum_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add advanced momentum features:
    - ROC (Rate of Change)
    - ADX (Average Directional Index)
    - Stochastic RSI
    """
    df = df.copy()

    # 1. Rate of Change (Price Momentum)
    # Measures the percentage change in price over n periods
    df["roc_10"] = df["Close"].pct_change(10) * 100
    df["roc_30"] = df["Close"].pct_change(30) * 100

    # 2. Stochastic RSI (Sensitive Momentum)
    # StochRSI = (RSI - MinRSI) / (MaxRSI - MinRSI)
    # More sensitive than standard RSI
    if "rsi" not in df.columns:
        df = add_rsi(df)

    min_rsi = df["rsi"].rolling(window=14).min()
    max_rsi = df["rsi"].rolling(window=14).max()
    df["stoch_rsi"] = (df["rsi"] - min_rsi) / (max_rsi - min_rsi + 1e-10)

    # 3. ADX (Average Directional Index - Trend Strength)
    # Requires +DI and -DI calculation
    high_diff = df["High"].diff()
    low_diff = df["Low"].diff()

    pos_dm = np.where((high_diff > 0) & (high_diff > -low_diff), high_diff, 0)
    neg_dm = np.where((low_diff < 0) & (-low_diff > high_diff), -low_diff, 0)

    # Smoothed TR, +DM, -DM
    tr = df["atr"] if "atr" in df.columns else add_atr(df)["atr"]

    # Smoothing (Wilder's smoothing)
    # Use EWM as approximation for Wilder's

    # Simplified approach for ADX to avoid complex loop
    # Using 14-period rolling sum for TR and DM
    # Standard ADX uses smoothed averages

    tr_s = tr.rolling(window=14).sum()
    pos_dm_s = pd.Series(pos_dm, index=df.index).rolling(window=14).sum()
    neg_dm_s = pd.Series(neg_dm, index=df.index).rolling(window=14).sum()

    pos_di = 100 * (pos_dm_s / (tr_s + 1e-10))
    neg_di = 100 * (neg_dm_s / (tr_s + 1e-10))

    dx = 100 * abs(pos_di - neg_di) / (pos_di + neg_di + 1e-10)
    df["adx"] = dx.rolling(window=14).mean()

    # Trend efficiency (Kaufman)
    # Abs change / Sum of individual changes
    change_abs = (df["Close"] - df["Close"].shift(10)).abs()
    volatility_sum = df["Close"].diff().abs().rolling(window=10).sum()
    df["efficiency_ratio"] = change_abs / (volatility_sum + 1e-10)

    return df


def add_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Add Relative Strength Index (RSI).

    RSI measures the speed and magnitude of price changes.
    Values above 70 indicate overbought, below 30 indicate oversold.
    """
    df = df.copy()

    # Calculate price changes
    delta = df["Close"].diff()

    # Separate gains and losses
    gains = delta.where(delta > 0, 0)
    losses = (-delta).where(delta < 0, 0)

    # Calculate average gains and losses
    avg_gains = gains.rolling(window=period, min_periods=1).mean()
    avg_losses = losses.rolling(window=period, min_periods=1).mean()

    # Calculate RSI
    rs = avg_gains / (avg_losses + 1e-10)  # Avoid division by zero
    df["rsi"] = 100 - (100 / (1 + rs))

    # Normalize to [-1, 1] range
    df["rsi_norm"] = (df["rsi"] - 50) / 50

    return df


def add_macd(
    df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    """
    Add Moving Average Convergence Divergence (MACD).

    MACD shows the relationship between two moving averages.
    """
    df = df.copy()

    # Calculate EMAs
    ema_fast = df["Close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["Close"].ewm(span=slow, adjust=False).mean()

    # MACD line
    df["macd_line"] = ema_fast - ema_slow

    # Signal line
    df["macd_signal"] = df["macd_line"].ewm(span=signal, adjust=False).mean()

    # MACD histogram
    df["macd_hist"] = df["macd_line"] - df["macd_signal"]

    # Normalize MACD values relative to price (use .values to avoid DataFrame issues)
    df["macd_norm"] = (df["macd_line"] / df["Close"]).values
    df["macd_hist_norm"] = (df["macd_hist"] / df["Close"]).values

    return df


def add_bollinger_bands(
    df: pd.DataFrame, period: int = 20, std_dev: int = 2
) -> pd.DataFrame:
    """
    Add Bollinger Bands.

    Bollinger Bands show price volatility and potential reversal points.
    """
    df = df.copy()

    # Calculate middle band (SMA)
    df["bb_middle"] = df["Close"].rolling(window=period).mean()

    # Calculate standard deviation
    std = df["Close"].rolling(window=period).std()

    # Upper and lower bands
    df["bb_upper"] = df["bb_middle"] + (std * std_dev)
    df["bb_lower"] = df["bb_middle"] - (std * std_dev)

    # Position within bands (normalized)
    # 0 = at lower band, 1 = at upper band
    band_width = df["bb_upper"] - df["bb_lower"]
    df["bb_position"] = (df["Close"] - df["bb_lower"]) / (band_width + 1e-10)

    # Band width relative to price
    df["bb_width"] = band_width / df["Close"]

    return df


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Add Average True Range (ATR).

    ATR measures market volatility.
    """
    df = df.copy()

    # True Range components
    high_low = df["High"] - df["Low"]
    high_close = abs(df["High"] - df["Close"].shift(1))
    low_close = abs(df["Low"] - df["Close"].shift(1))

    # True Range
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

    # ATR
    df["atr"] = true_range.rolling(window=period).mean()

    # Normalized ATR (as percentage of price)
    df["atr_norm"] = df["atr"] / df["Close"]

    return df


def add_volume_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add volume-based features."""
    df = df.copy()

    # Volume normalized by 20-day average
    df["volume_norm"] = df["Volume"] / df["Volume"].rolling(window=20).mean()
    df["volume_norm"] = df["Volume"] / (df["Volume"].rolling(window=20).mean() + 1e-10)

    # Legacy feature support
    df["volume_change"] = df["Volume"].pct_change()

    # 1. On-Balance Volume (OBV)
    # Measures buying vs selling pressure
    obv_change = np.where(
        df["Close"] > df["Close"].shift(1),
        df["Volume"],
        np.where(df["Close"] < df["Close"].shift(1), -df["Volume"], 0),
    )
    df["obv"] = pd.Series(obv_change, index=df.index).cumsum()
    # Normalize OBV slope (OBV - SMA(OBV)) / SMA(Volume)
    avg_volume = df["Volume"].rolling(window=20).mean()
    df["obv_slope"] = (df["obv"] - df["obv"].rolling(window=20).mean()) / (
        avg_volume + 1e-10
    )

    # 2. VWAP (Volume Weighted Average Price)
    # Standard intra-day VWAP resets daily, but for daily data we use rolling VWAP
    cum_vol_price = (df["Close"] * df["Volume"]).rolling(window=20).sum()
    cum_vol = df["Volume"].rolling(window=20).sum()
    df["vwap_rolling"] = cum_vol_price / (cum_vol + 1e-10)
    df["close_vs_vwap"] = (df["Close"] / df["vwap_rolling"]) - 1

    # 3. Elder Force Index (EFI)
    # (Close - PrevClose) * Volume
    df["efi"] = (df["Close"] - df["Close"].shift(1)) * df["Volume"]
    # Normalize EFI by Average Volume * Price (to make it relative)
    avg_vol_price = df["Volume"].rolling(20).mean() * df["Close"].rolling(20).mean()
    df["efi_norm"] = df["efi"].rolling(13).mean() / (avg_vol_price + 1e-10)

    # 4. Volume Microstructure (Buying vs Selling Pressure)
    # Estimate buying volume vs selling volume based on price movement
    # Close > Open -> Buying; Close < Open -> Selling
    df["pos_volume"] = np.where(df["Close"] > df["Open"], df["Volume"], 0)
    df["neg_volume"] = np.where(df["Close"] <= df["Open"], df["Volume"], 0)

    # Volume Ratio: Pos / Total (0 to 1)
    # Smoothed over 5 days to reduce noise
    pos_sum = pd.Series(df["pos_volume"]).rolling(5).sum()
    total_sum = df["Volume"].rolling(5).sum()
    df["volume_ratio"] = pos_sum / (total_sum + 1e-10)

    # 5. Chaikin Money Flow (CMF)
    # ( (Close - Low) - (High - Close) ) / (High - Low) * Volume
    mf_multiplier = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / (
        df["High"] - df["Low"] + 1e-10
    )
    mf_volume = mf_multiplier * df["Volume"]
    df["cmf"] = mf_volume.rolling(window=20).sum() / (
        df["Volume"].rolling(window=20).sum() + 1e-10
    )

    return df


def add_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    """Add Simple and Exponential Moving Averages."""
    df = df.copy()

    for period in [20, 50, 200]:
        df[f"sma_{period}"] = df["Close"].rolling(window=period).mean()
        df[f"price_vs_sma_{period}"] = (df["Close"] / df[f"sma_{period}"]) - 1

    # SMA crossovers
    df["sma_20_50_cross"] = df["sma_20"] / df["sma_50"] - 1

    # Exponential Moving Average
    df["ema_12"] = df["Close"].ewm(span=12, adjust=False).mean()
    df["price_vs_ema12"] = df["Close"] / df["ema_12"] - 1

    return df


def add_regime_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add composite regime features for position sizing and curriculum learning.

    Features:
    - favorable_long_regime: Composite score (0-1) for dynamic position sizing
    - difficulty_score: How hard this period is to trade (for curriculum learning)
    """
    df = df.copy()

    # 1. Component indicators for regime (ensure they exist)
    # Uptrend: Price above SMA_50
    if "sma_50" not in df.columns:
        df["sma_50"] = df["Close"].rolling(window=50).mean()
    df["in_uptrend"] = (df["Close"] > df["sma_50"]).astype(float)

    # Low volatility regime: ATR_norm below median
    if "atr_norm" not in df.columns:
        df = add_atr(df)
    vol_median = df["atr_norm"].rolling(100).median()
    df["vol_regime_low"] = (df["atr_norm"] < vol_median).astype(float)

    # High volume regime: Volume above average
    if "volume_norm" not in df.columns:
        df["volume_norm"] = df["Volume"] / (df["Volume"].rolling(20).mean() + 1e-10)
    df["volume_regime_high"] = (df["volume_norm"] > 1.0).astype(float)

    # Momentum regime: 20-day momentum positive
    df["momentum_20d"] = df["Close"].pct_change(20)
    df["momentum_regime_pos"] = (df["momentum_20d"] > 0).astype(float)

    # 2. Composite Favorable Long Score (0-1)
    # Higher = better conditions for long positions
    df["favorable_long_regime"] = (
        df["in_uptrend"] * 0.4  # Trend is most important
        + df["vol_regime_low"] * 0.3  # Low vol = easier
        + df["volume_regime_high"] * 0.2  # High vol = conviction
        + df["momentum_regime_pos"] * 0.1  # Momentum confirmation
    )

    # 3. Difficulty Score (0-1) for curriculum learning
    # Higher = harder to trade (more volatile, less trending)

    # Volatility component (normalized to 0-1)
    vol_z = (df["atr_norm"] - df["atr_norm"].rolling(100).mean()) / (
        df["atr_norm"].rolling(100).std() + 1e-10
    )
    vol_score = (vol_z.clip(-2, 2) + 2) / 4  # Normalize to 0-1

    # Trendiness component (inverse - low trend = hard)
    # Use efficiency ratio: high = trending, low = choppy
    if "efficiency_ratio" not in df.columns:
        change_abs = (df["Close"] - df["Close"].shift(10)).abs()
        volatility_sum = df["Close"].diff().abs().rolling(10).sum()
        df["efficiency_ratio"] = change_abs / (volatility_sum + 1e-10)
    trend_score = 1 - df["efficiency_ratio"].clip(
        0, 1
    )  # Invert: low trend = high difficulty

    # Drawdown component (in drawdown = harder)
    rolling_max = df["Close"].rolling(50).max()
    current_dd = (rolling_max - df["Close"]) / (rolling_max + 1e-10)
    dd_score = current_dd.clip(0, 0.5) * 2  # Normalize 0-50% DD to 0-1

    # Composite Difficulty Score
    df["difficulty_score"] = (
        vol_score * 0.4  # Volatility is biggest factor
        + trend_score * 0.4  # Choppiness matters
        + dd_score * 0.2  # In drawdown is harder
    )

    return df


def get_feature_names() -> list:
    """Get list of all feature column names added by technical indicators."""
    return [
        # Price features (scale invariant)
        "return_1d",
        "return_5d",
        "return_20d",
        "price_norm",
        "daily_range",
        "gap",
        "price_position",  # 0-1 position within bar
        "body_to_range",  # Candle strength
        # Momentum
        "rsi",
        "rsi_norm",
        "roc_10",
        "roc_30",
        "stoch_rsi",
        "adx",
        "efficiency_ratio",
        # MACD (normalized)
        "macd_line",
        "macd_signal",
        "macd_hist",
        "macd_norm",
        "macd_hist_norm",
        # Bollinger Bands
        "bb_position",  # Position within bands (0-1)
        "bb_width",  # Band width relative to price
        # ATR
        "atr_norm",  # ATR as % of price
        # Volume Microstructure
        "volume_norm",  # Volume relative to 20-day avg
        "volume_change",
        "obv_slope",  # OBV trend
        "close_vs_vwap",  # Price vs VWAP (scale invariant)
        "efi_norm",  # Elder Force Index normalized
        "volume_ratio",  # Buying vs total volume (0-1)
        "cmf",  # Chaikin Money Flow
        # Moving Averages (scale invariant)
        "price_vs_sma_20",
        "price_vs_sma_50",
        "price_vs_sma_200",
        "sma_20_50_cross",
        "price_vs_ema12",
        # Regime Features
        "in_uptrend",  # Binary: above SMA_50
        "vol_regime_low",  # Binary: volatility below median
        "volume_regime_high",  # Binary: volume above average
        "momentum_regime_pos",  # Binary: 20d momentum positive
        "favorable_long_regime",  # Composite score (0-1)
        "difficulty_score",  # How hard to trade (0-1)
    ]
