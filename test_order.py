#!/usr/bin/env python3
"""
Simple test script to debug OANDA order placement.
Run with: python test_order.py
"""

import os
from dotenv import load_dotenv
import oandapyV20
from oandapyV20 import API
from oandapyV20.endpoints import accounts, orders, pricing

load_dotenv()


def test_order():
    api_key = os.getenv("OANDA_API_KEY")
    account_id = os.getenv("OANDA_ACCOUNT_ID")
    environment = os.getenv("OANDA_ENVIRONMENT", "practice")

    print("=" * 60)
    print("OANDA Order Test")
    print("=" * 60)
    print(f"Account ID: {account_id}")
    print(f"Environment: {environment}")
    print(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    print()

    # Connect
    api = API(access_token=api_key, environment=environment)

    # 1. Test account access
    print("1. Testing account access...")
    try:
        endpoint = accounts.AccountSummary(accountID=account_id)
        response = api.request(endpoint)
        account = response["account"]
        print(f"   ✅ Connected!")
        print(f"   Balance: ${float(account['balance']):,.2f}")
        print(f"   NAV: ${float(account['NAV']):,.2f}")
        print(f"   Open Positions: {account.get('openPositionCount', 0)}")
        print(f"   Open Trades: {account.get('openTradeCount', 0)}")
    except Exception as e:
        print(f"   ❌ Account access failed: {e}")
        return

    # 2. Test pricing
    print("\n2. Testing pricing...")
    instrument = "EUR_USD"
    try:
        params = {"instruments": instrument}
        endpoint = pricing.PricingInfo(accountID=account_id, params=params)
        response = api.request(endpoint)
        if response["prices"]:
            price = response["prices"][0]
            bid = float(price["bids"][0]["price"])
            ask = float(price["asks"][0]["price"])
            print(f"   ✅ {instrument}: Bid={bid:.5f}, Ask={ask:.5f}")
        else:
            print(f"   ❌ No pricing data")
            return
    except Exception as e:
        print(f"   ❌ Pricing failed: {e}")
        return

    # 3. Test order placement
    print("\n3. Testing order placement...")
    print(f"   Attempting: BUY 100 units of {instrument}")

    # Small test order - 100 units (about $10 worth)
    sl_price = round(bid - 0.0030, 5)  # 30 pip stop loss

    order_data = {
        "order": {
            "type": "MARKET",
            "instrument": instrument,
            "units": "100",  # Very small - 100 units
            "timeInForce": "IOC",  # Immediate or Cancel
            "positionFill": "DEFAULT",
            "stopLossOnFill": {
                "price": str(sl_price),
                "timeInForce": "GTC",
            },
        }
    }

    print(f"   Order data: {order_data}")
    print()

    try:
        endpoint = orders.OrderCreate(accountID=account_id, data=order_data)
        response = api.request(endpoint)

        print("   📄 Full Response:")
        import json

        print(json.dumps(response, indent=2))

        if "orderFillTransaction" in response:
            fill = response["orderFillTransaction"]
            print(f"\n   ✅ ORDER FILLED!")
            print(f"   Trade ID: {fill['id']}")
            print(f"   Price: {fill['price']}")
            print(f"   Units: {fill['units']}")
        elif "orderCancelTransaction" in response:
            cancel = response["orderCancelTransaction"]
            print(f"\n   ⚠️  ORDER CANCELLED!")
            print(f"   Reason: {cancel.get('reason', 'Unknown')}")
        else:
            print(f"\n   ❓ Unexpected response structure")

    except Exception as e:
        print(f"   ❌ Order failed with exception: {e}")

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


if __name__ == "__main__":
    test_order()
