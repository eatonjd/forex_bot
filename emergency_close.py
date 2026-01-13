import os
from dotenv import load_dotenv
from oandapyV20 import API
from oandapyV20.endpoints.positions import PositionDetails, PositionClose


def close_usd_jpy_on_account(env_name, is_live=False):
    load_dotenv()

    if is_live:
        api_key = os.getenv("OANDA_API_KEY_LIVE")
        account_id = os.getenv("OANDA_ACCOUNT_ID_LIVE")
        env = "live"
    else:
        api_key = os.getenv("OANDA_API_KEY")
        account_id = os.getenv("OANDA_ACCOUNT_ID")
        env = "practice"

    if not api_key or not account_id:
        print(f"⚠️ Skipping {env_name}: Missing credentials")
        return

    print(f"🔍 Checking {env_name} ({env}) account {account_id}...")
    api = API(access_token=api_key, environment=env)

    try:
        # Check current position
        r = PositionDetails(accountID=account_id, instrument="USD_JPY")
        api.request(r)
        pos = r.response.get("position", {})

        long_units = int(pos.get("long", {}).get("units", 0))
        short_units = int(pos.get("short", {}).get("units", 0))

        if long_units == 0 and short_units == 0:
            print(f"🟢 No open USD_JPY position on {env_name}")
            return

        if long_units > 0:
            data = {"longUnits": "ALL"}
            side = "LONG"
        else:
            data = {"shortUnits": "ALL"}
            side = "SHORT"

        print(f"🔴 Found {side} position. Closing {env_name}...")
        r_close = PositionClose(accountID=account_id, instrument="USD_JPY", data=data)
        api.request(r_close)

        print(f"✅ Successfully closed {env_name} USD_JPY position.")

    except Exception as e:
        print(f"❌ Error on {env_name}: {e}")


if __name__ == "__main__":
    close_usd_jpy_on_account("DEMO", is_live=False)
    close_usd_jpy_on_account("LIVE", is_live=True)
