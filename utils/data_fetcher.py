"""
Data fetching utilities for the Trading Bot.

Downloads stock data from Yahoo Finance and prepares it for training.
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from typing import Tuple, Optional
import warnings

from utils.indicators import add_technical_indicators


def fetch_stock_data(
    symbol: str,
    start_date: str = "2020-01-01",
    end_date: Optional[str] = None,
    interval: str = "1d"
) -> pd.DataFrame:
    """
    Download stock data from Yahoo Finance.
    
    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL')
        start_date: Start date in 'YYYY-MM-DD' format
        end_date: End date in 'YYYY-MM-DD' format (defaults to today)
        interval: Data interval ('1d', '1h', '5m', etc.)
        
    Returns:
        DataFrame with OHLCV data
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    print(f"📥 Downloading {symbol} data from {start_date} to {end_date}...")
    
    # Download data
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start_date, end=end_date, interval=interval)
    
    if df.empty:
        raise ValueError(f"No data found for {symbol}")
    
    # Clean up the dataframe
    df = df.reset_index()
    
    # Standardize column names
    if "Date" in df.columns:
        df = df.rename(columns={"Date": "Datetime"})
    
    # Keep only OHLCV columns
    required_cols = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
    available_cols = [col for col in required_cols if col in df.columns]
    df = df[available_cols]
    
    # Remove any rows with NaN values in price columns
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    
    print(f"✅ Downloaded {len(df)} data points")
    
    return df


def prepare_data(
    df: pd.DataFrame,
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
    add_indicators: bool = True
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Prepare data for training by adding indicators and splitting.
    
    Args:
        df: Raw OHLCV DataFrame
        train_ratio: Fraction of data for training
        val_ratio: Fraction of data for validation
        add_indicators: Whether to add technical indicators
        
    Returns:
        Tuple of (train_df, val_df, test_df)
    """
    # Make a copy to avoid modifying the original
    df = df.copy()
    
    # Add technical indicators
    if add_indicators:
        print("📊 Adding technical indicators...")
        df = add_technical_indicators(df)
    
    # Drop any rows with NaN values (from indicator calculations)
    initial_len = len(df)
    df = df.dropna()
    dropped = initial_len - len(df)
    if dropped > 0:
        print(f"⚠️  Dropped {dropped} rows with NaN values")
    
    # Calculate split indices
    n = len(df)
    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + val_ratio))
    
    # Split the data
    train_df = df.iloc[:train_end].reset_index(drop=True)
    val_df = df.iloc[train_end:val_end].reset_index(drop=True)
    test_df = df.iloc[val_end:].reset_index(drop=True)
    
    print(f"📈 Data split: Train={len(train_df)}, Val={len(val_df)}, Test={len(test_df)}")
    
    return train_df, val_df, test_df


def get_price_data_only(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract only price-related columns for visualization.
    
    Args:
        df: DataFrame with OHLCV and indicators
        
    Returns:
        DataFrame with only OHLCV columns
    """
    ohlcv_cols = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
    available = [col for col in ohlcv_cols if col in df.columns]
    return df[available].copy()


def create_sample_data(n_days: int = 500, seed: int = 42) -> pd.DataFrame:
    """
    Create synthetic stock data for testing.
    
    Args:
        n_days: Number of days of data to generate
        seed: Random seed for reproducibility
        
    Returns:
        DataFrame with synthetic OHLCV data
    """
    np.random.seed(seed)
    
    # Start price
    price = 100.0
    
    dates = pd.date_range(end=datetime.now(), periods=n_days, freq='D')
    
    data = []
    for date in dates:
        # Random walk with drift
        daily_return = np.random.normal(0.0005, 0.02)  # Mean slightly positive
        price *= (1 + daily_return)
        
        # Generate OHLC from close
        high = price * (1 + abs(np.random.normal(0, 0.01)))
        low = price * (1 - abs(np.random.normal(0, 0.01)))
        open_price = low + (high - low) * np.random.random()
        
        volume = int(np.random.lognormal(15, 1))
        
        data.append({
            "Datetime": date,
            "Open": open_price,
            "High": high,
            "Low": low,
            "Close": price,
            "Volume": volume
        })
    
    df = pd.DataFrame(data)
    return df
