"""
Full Pair Scanner Test with RL Model

Tests the complete pair scanner with RL model predictions and trend analysis.
"""

import sys

sys.path.append("/Users/eatonjd/Github/forex_bot")

from utils.oanda_connector import OANDAConnector
from utils.pair_scanner import ForexPairScanner
from utils.forex_decision_reasoning import ForexDecisionReasoner
from stable_baselines3 import PPO
import json

print("=" * 60)
print("🔍 FULL PAIR SCANNER TEST (with RL Model)")
print("=" * 60)

# Initialize components
print("\n1. Connecting to OANDA...")
oanda = OANDAConnector(environment="practice")
print(f"   ✅ Connected - Account: {oanda.account_id}")

print("\n2. Loading RL model...")
model = PPO.load("models/ppo_improved_final", device="cpu")
print("   ✅ Model loaded")

print("\n3. Initializing reasoner...")
reasoner = ForexDecisionReasoner()
print("   ✅ Reasoner ready")

print("\n4. Creating pair scanner...")
scanner = ForexPairScanner(oanda, model, reasoner)
print("   ✅ Scanner ready")

print("\n5. Scanning major forex pairs with RL model...")
print("=" * 60)

# Scan pairs
top_pairs = scanner.scan_pairs(current_symbols=["EUR_USD", "GBP_USD"], top_n=5)

# Display results
if top_pairs:
    scanner.print_scan_results(top_pairs)

    # Save results for dashboard
    results = {
        "timestamp": "2025-12-20 11:30:00",
        "pairs": [
            {
                "symbol": p.symbol,
                "score": p.total_score,
                "spread": p.details["spread_pips"],
                "trend": p.details["trend"],
            }
            for p in top_pairs
        ],
    }

    with open("pair_scanner_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n✅ Results saved to pair_scanner_results.json")
    print(f"   Dashboard will display these results with trends!")
else:
    print("\n⚠️  No pairs could be scanned")

print("\n" + "=" * 60)
print("✅ Full pair scanner test complete!")
print("=" * 60)
