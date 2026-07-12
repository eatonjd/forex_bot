import os
from oandapyV20 import API
from command_center import fetch_account_data

api = API(access_token=os.getenv("OANDA_API_KEY"), environment="practice")
acc1 = fetch_account_data(api, os.getenv("OANDA_ACCOUNT_ID"))
print("ACC1 (-001):", acc1["equity"], acc1["error"])

acc2 = fetch_account_data(api, os.getenv("OANDA_ACCOUNT_ID_VOL", "101-001-38009813-002"))
print("ACC2 (-002):", acc2["equity"], acc2["error"])

live_api = API(access_token=os.getenv("OANDA_API_KEY_LIVE"), environment="live")
live = fetch_account_data(live_api, os.getenv("OANDA_ACCOUNT_ID_LIVE"))
print("LIVE:", live["equity"], live["error"])
