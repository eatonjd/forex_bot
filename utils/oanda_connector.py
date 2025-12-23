"""
OANDA Trading Connector

Handles connection to OANDA API for paper/live trading.
Compatible with RL model + Position Manager integration.

Author: Forex Bot Team
Created: 2025-12-19
"""

import os
from typing import Dict, Optional, List
from datetime import datetime
import oandapyV20
from oandapyV20 import API
from oandapyV20.endpoints import accounts, orders, positions, pricing, instruments
from oandapyV20.exceptions import V20Error
from dotenv import load_dotenv

load_dotenv()


class OANDAConnector:
    """
    OANDA API connector for forex trading.

    Supports:
    - Paper trading (practice environment)
    - Live trading (live environment)
    - Real-time pricing
    - Order execution
    - Position management
    """

    def __init__(self, environment: str = "practice", use_real_spreads: bool = None):
        """
        Initialize OANDA connection.

        Args:
            environment: 'practice' for demo, 'live' for real trading
            use_real_spreads: Override spreads with Alpha Vantage (default: from USE_REAL_SPREADS env)
        """
        self.api_key = os.getenv("OANDA_API_KEY")
        self.account_id = os.getenv("OANDA_ACCOUNT_ID")
        self.environment = environment

        if not self.api_key:
            raise ValueError("OANDA_API_KEY environment variable not set")

        if not self.account_id:
            raise ValueError("OANDA_ACCOUNT_ID environment variable not set")

        # Initialize API
        self.api = API(access_token=self.api_key, environment=environment)

        # Initialize spread provider for real spreads
        self.use_real_spreads = (
            use_real_spreads
            if use_real_spreads is not None
            else (os.getenv("USE_REAL_SPREADS", "false").lower() == "true")
        )
        self.spread_provider = None

        if self.use_real_spreads:
            try:
                from utils.spread_provider import AlphaVantageSpreadProvider

                self.spread_provider = AlphaVantageSpreadProvider()
                print(f"✅ Real-time spreads enabled (Alpha Vantage)")
            except Exception as e:
                print(f"⚠️  Could not initialize spread provider: {e}")
                print("   Using OANDA spreads")
                self.use_real_spreads = False

        print(f"✅ Connected to OANDA ({environment} environment)")
        print(f"   Account: {self.account_id}")

    def get_account_summary(self) -> Dict:
        """Get account balance and summary"""
        try:
            endpoint = accounts.AccountSummary(accountID=self.account_id)
            response = self.api.request(endpoint)

            account = response["account"]
            return {
                "balance": float(account["balance"]),
                "currency": account["currency"],
                "unrealized_pl": float(account.get("unrealizedPL", 0)),
                "nav": float(account["NAV"]),
                "margin_used": float(account.get("marginUsed", 0)),
                "margin_available": float(account.get("marginAvailable", 0)),
                "open_positions": int(account.get("openPositionCount", 0)),
                "open_trades": int(account.get("openTradeCount", 0)),
            }
        except V20Error as e:
            print(f"Error getting account: {e}")
            return {}

    def get_current_price(self, instrument: str) -> Optional[Dict]:
        """
        Get current bid/ask price for instrument.

        Args:
            instrument: e.g., 'EUR_USD', 'GBP_USD'
        """
        try:
            params = {"instruments": instrument}
            endpoint = pricing.PricingInfo(accountID=self.account_id, params=params)
            response = self.api.request(endpoint)

            if response["prices"]:
                price_data = response["prices"][0]
                bid = float(price_data["bids"][0]["price"])
                ask = float(price_data["asks"][0]["price"])
                spread = ask - bid

                # Override spread with Alpha Vantage if enabled
                if self.use_real_spreads and self.spread_provider:
                    # Convert pips to price
                    pip_size = 0.01 if "JPY" in instrument else 0.0001

                    real_spread_pips = self.spread_provider.get_spread(instrument)
                    if real_spread_pips is not None:
                        spread = real_spread_pips * pip_size
                    else:
                        # Use typical spread as fallback
                        typical_pips = self.spread_provider.get_typical_spread(
                            instrument
                        )
                        spread = typical_pips * pip_size

                return {
                    "instrument": instrument,
                    "bid": bid,
                    "ask": ask,
                    "spread": spread,
                    "time": price_data["time"],
                }
            return None
        except V20Error as e:
            print(f"Error getting price: {e}")
            return None

    def place_market_order(
        self,
        instrument: str,
        units: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Optional[Dict]:
        """
        Place market order.

        Args:
            instrument: e.g., 'EUR_USD'
            units: Positive for buy, negative for sell
            stop_loss: Optional SL price
            take_profit: Optional TP price
        """
        try:
            order_data = {
                "order": {
                    "type": "MARKET",
                    "instrument": instrument,
                    "units": str(units),
                    "timeInForce": "FOK",
                    "positionFill": "DEFAULT",
                }
            }

            # Add SL/TP if provided
            if stop_loss:
                order_data["order"]["stopLossOnFill"] = {
                    "price": str(stop_loss),
                    "timeInForce": "GTC",
                }

            if take_profit:
                order_data["order"]["takeProfitOnFill"] = {
                    "price": str(take_profit),
                    "timeInForce": "GTC",
                }

            endpoint = orders.OrderCreate(accountID=self.account_id, data=order_data)
            response = self.api.request(endpoint)

            if "orderFillTransaction" in response:
                fill = response["orderFillTransaction"]
                return {
                    "order_id": fill["id"],
                    "instrument": fill["instrument"],
                    "units": float(fill["units"]),
                    "price": float(fill["price"]),
                    "pl": float(fill.get("pl", 0)),
                    "time": fill["time"],
                }
            return response

        except V20Error as e:
            print(f"Error placing order: {e}")
            return None

    def get_open_positions(self) -> List[Dict]:
        """Get all open positions"""
        try:
            endpoint = positions.OpenPositions(accountID=self.account_id)
            response = self.api.request(endpoint)

            positions_list = []
            for pos in response.get("positions", []):
                if (
                    float(pos["long"]["units"]) != 0
                    or float(pos["short"]["units"]) != 0
                ):
                    positions_list.append(
                        {
                            "instrument": pos["instrument"],
                            "long_units": float(pos["long"]["units"]),
                            "short_units": float(pos["short"]["units"]),
                            "unrealized_pl": float(pos["unrealizedPL"]),
                            "avg_price": float(
                                pos["long"].get(
                                    "averagePrice", pos["short"].get("averagePrice", 0)
                                )
                            ),
                        }
                    )

            return positions_list
        except V20Error as e:
            print(f"Error getting positions: {e}")
            return []

    def close_position(
        self, instrument: str, long_units: str = "ALL", short_units: str = "ALL"
    ) -> Optional[Dict]:
        """Close position for instrument"""
        try:
            data = {"longUnits": long_units, "shortUnits": short_units}
            endpoint = positions.PositionClose(
                accountID=self.account_id, instrument=instrument, data=data
            )
            response = self.api.request(endpoint)
            return response
        except V20Error as e:
            print(f"Error closing position: {e}")
            return None

    def get_candles(
        self, instrument: str, granularity: str = "H1", count: int = 500
    ) -> List[Dict]:
        """
        Get historical candlestick data.

        Args:
            instrument: e.g., 'EUR_USD'
            granularity: 'M1', 'M5', 'H1', 'D' etc.
            count: Number of candles
        """
        try:
            params = {"granularity": granularity, "count": count}
            endpoint = instruments.InstrumentsCandles(
                instrument=instrument, params=params
            )
            response = self.api.request(endpoint)

            candles = []
            for candle in response["candles"]:
                if candle["complete"]:
                    candles.append(
                        {
                            "time": candle["time"],
                            "open": float(candle["mid"]["o"]),
                            "high": float(candle["mid"]["h"]),
                            "low": float(candle["mid"]["l"]),
                            "close": float(candle["mid"]["c"]),
                            "volume": int(candle["volume"]),
                        }
                    )

            return candles
        except V20Error as e:
            print(f"Error getting candles: {e}")
            return []


if __name__ == "__main__":
    # Test connection
    print("=" * 60)
    print("Testing OANDA Connection")
    print("=" * 60)
    print()

    try:
        # Connect
        oanda = OANDAConnector(environment="practice")

        # Get account info
        print("\n📊 Account Summary:")
        account = oanda.get_account_summary()
        if account:
            print(f"   Balance: ${account['balance']:,.2f} {account['currency']}")
            print(f"   NAV: ${account['nav']:,.2f}")
            print(f"   Unrealized P/L: ${account['unrealized_pl']:,.2f}")
            print(f"   Open Positions: {account['open_positions']}")
            print(f"   Open Trades: {account['open_trades']}")

        # Get current price
        print("\n💹 EUR/USD Price:")
        price = oanda.get_current_price("EUR_USD")
        if price:
            print(f"   Bid: {price['bid']}")
            print(f"   Ask: {price['ask']}")
            print(f"   Spread: {price['spread']:.5f}")

        # Get positions
        print("\n📍 Open Positions:")
        positions = oanda.get_open_positions()
        if positions:
            for pos in positions:
                print(
                    f"   {pos['instrument']}: {pos['long_units']} units, P/L: ${pos['unrealized_pl']:.2f}"
                )
        else:
            print("   No open positions")

        print("\n✅ Connection test successful!")

    except Exception as e:
        print(f"\n❌ Connection test failed: {e}")
        import traceback

        traceback.print_exc()
