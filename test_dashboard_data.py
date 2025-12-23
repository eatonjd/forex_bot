"""
Simple test to verify dashboard data loading
"""

import json
from pathlib import Path

print("Testing dashboard data loading...")
print("=" * 60)

# Load bot state
status_file = Path("bot_state.json")
if status_file.exists():
    with open(status_file, "r") as f:
        bot_status = json.load(f)

    print("✅ Bot state loaded")
    print(f"Hold reasons: {bot_status.get('hold_reasons', {})}")
    print(f"Type: {type(bot_status.get('hold_reasons'))}")
    print(f"Is truthy: {bool(bot_status.get('hold_reasons'))}")
    print(f"Length > 0: {len(bot_status.get('hold_reasons', {})) > 0}")

    # Test the exact condition from dashboard
    hold_reasons = bot_status.get("hold_reasons", {})
    if hold_reasons and len(hold_reasons) > 0:
        print("\n✅ Chart SHOULD display")
        print(f"Labels: {list(hold_reasons.keys())}")
        print(f"Values: {list(hold_reasons.values())}")
    else:
        print("\n❌ Chart will NOT display")
        print(f"hold_reasons value: {hold_reasons}")
else:
    print("❌ bot_state.json not found")

print("=" * 60)
