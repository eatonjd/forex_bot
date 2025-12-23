#!/usr/bin/env python3
"""
Get OANDA Account ID

Quick script to fetch your OANDA account ID using the API key.
Run this once to get your account ID for .env file.
"""

import os
from dotenv import load_dotenv
import oandapyV20
from oandapyV20 import API
from oandapyV20.endpoints import accounts

load_dotenv()

print("=" * 60)
print("OANDA Account ID Fetcher")
print("=" * 60)
print()

api_key = os.getenv("OANDA_API_KEY")

if not api_key:
    print("❌ OANDA_API_KEY not found in .env file")
    print("\nPlease add to .env:")
    print("OANDA_API_KEY=your_api_key_here")
    exit(1)

print(f"✅ API Key found: {api_key[:20]}...")
print()

# Try both environments
for env in ["practice", "live"]:
    try:
        print(f"🔍 Checking {env} environment...")
        api = API(access_token=api_key, environment=env)
        endpoint = accounts.AccountList()
        response = api.request(endpoint)

        if "accounts" in response and len(response["accounts"]) > 0:
            print(f"\n✅ Found accounts in {env}:")
            for acc in response["accounts"]:
                print(f"\n   Account ID: {acc['id']}")
                print(f"   Tags: {acc.get('tags', [])}")

            # Get first account details
            account_id = response["accounts"][0]["id"]
            print(f"\n📋 Add this to your .env file:")
            print(f"OANDA_ACCOUNT_ID={account_id}")
            print(f"OANDA_ENVIRONMENT={env}")

            break
        else:
            print(f"   No accounts found in {env}")

    except Exception as e:
        print(f"   Error: {e}")

print("\n" + "=" * 60)
