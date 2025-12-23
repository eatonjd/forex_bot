"""
Alpha Vantage Spread Provider

Fetches real-time bid/ask prices from Alpha Vantage to calculate accurate forex spreads.
Uses caching to respect free tier limits (5 req/min, 500 req/day).
"""

import requests
from typing import Dict, Optional
from datetime import datetime, timedelta
import os


class AlphaVantageSpreadProvider:
    """Provides real-time forex spreads using Alpha Vantage API"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Alpha Vantage spread provider

        Args:
            api_key: Alpha Vantage API key (or set ALPHA_VANTAGE_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("ALPHA_VANTAGE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Alpha Vantage API key required. Set ALPHA_VANTAGE_API_KEY env var or pass to constructor."
            )

        self.base_url = "https://www.alphavantage.co/query"
        self.cache = {}  # {symbol: {spread, timestamp}}
        self.cache_duration = timedelta(minutes=5)  # Cache for 5 minutes

        print(f"✅ Alpha Vantage Spread Provider initialized")

    def get_spread(self, symbol: str) -> Optional[float]:
        """
        Get current spread for a forex pair in pips

        Args:
            symbol: Forex pair (e.g., "EUR_USD")

        Returns:
            Spread in pips, or None if unavailable
        """
        # Check cache first
        if symbol in self.cache:
            cached = self.cache[symbol]
            if datetime.now() - cached["timestamp"] < self.cache_duration:
                return cached["spread"]

        # Convert OANDA format to Alpha Vantage format
        # EUR_USD -> EUR/USD or EURUSD
        from_currency, to_currency = symbol.split("_")

        try:
            # Fetch from Alpha Vantage
            params = {
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": from_currency,
                "to_currency": to_currency,
                "apikey": self.api_key,
            }

            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Check for API limit errors
            if "Note" in data:
                print(
                    f"⚠️  Alpha Vantage API limit reached. Using cached or fallback spreads."
                )
                return None

            if "Error Message" in data:
                print(f"⚠️  Alpha Vantage error: {data['Error Message']}")
                return None

            # Extract bid/ask
            rate_data = data.get("Realtime Currency Exchange Rate", {})
            bid = float(rate_data.get("8. Bid Price", 0))
            ask = float(rate_data.get("9. Ask Price", 0))

            if bid == 0 or ask == 0:
                print(f"⚠️  No bid/ask data for {symbol}")
                return None

            # Calculate spread in pips
            # For JPY pairs, 1 pip = 0.01, for others 1 pip = 0.0001
            pip_size = 0.01 if "JPY" in symbol else 0.0001
            spread_pips = (ask - bid) / pip_size

            # Cache result
            self.cache[symbol] = {"spread": spread_pips, "timestamp": datetime.now()}

            return spread_pips

        except requests.RequestException as e:
            print(f"⚠️  Error fetching spread from Alpha Vantage: {e}")
            return None
        except (KeyError, ValueError) as e:
            print(f"⚠️  Error parsing Alpha Vantage response: {e}")
            return None

    def get_typical_spread(self, symbol: str) -> float:
        """
        Get typical spread for a pair (fallback when API unavailable)

        Based on typical broker spreads for major pairs
        """
        typical_spreads = {
            "EUR_USD": 0.9,
            "GBP_USD": 1.8,
            "USD_JPY": 0.7,
            "AUD_USD": 1.2,
            "USD_CAD": 1.5,
            "NZD_USD": 2.0,
            "EUR_GBP": 1.5,
            "EUR_JPY": 1.8,
            "GBP_JPY": 2.5,
            "USD_CHF": 1.3,
        }
        return typical_spreads.get(symbol, 2.0)  # Default 2.0 pips


def test_spread_provider():
    """Test the spread provider"""
    print("=" * 60)
    print("Testing Alpha Vantage Spread Provider")
    print("=" * 60)

    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        print("⚠️  ALPHA_VANTAGE_API_KEY not set")
        print("   Set it in .env file or export ALPHA_VANTAGE_API_KEY=your_key")
        return

    provider = AlphaVantageSpreadProvider(api_key)

    test_pairs = ["EUR_USD", "GBP_USD", "USD_JPY"]

    for pair in test_pairs:
        spread = provider.get_spread(pair)
        if spread:
            print(f"✅ {pair}: {spread:.1f} pips")
        else:
            typical = provider.get_typical_spread(pair)
            print(f"⚠️  {pair}: Using typical spread {typical:.1f} pips")

    print("=" * 60)


if __name__ == "__main__":
    test_spread_provider()
