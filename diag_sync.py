from utils.oanda_connector import OANDAConnector
import json
import os


def check_sync():
    oanda = OANDAConnector()
    print("OANDA Account:", oanda.account_id)

    # 1. Get real positions from OANDA
    real_positions = oanda.get_open_positions()
    print(f"\nOANDA Real Positions ({len(real_positions)}):")
    for pos in real_positions:
        print(
            f"  - {pos['instrument']}: {pos['long_units'] + pos['short_units']} units"
        )

    # 2. Get bot state from GCS (or just check what we know)
    print("\nBot 'Ghost' Positions to check...")
    # These were seen in the logs
    to_check = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"]

    real_instruments = [p["instrument"] for p in real_positions]

    for instr in to_check:
        if instr in real_instruments:
            print(f"  ✅ {instr}: Match")
        else:
            print(f"  ❌ {instr}: GHOST (Bot thinks it has it, OANDA doesn't)")


if __name__ == "__main__":
    check_sync()
