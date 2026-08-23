#!/usr/bin/env python3
"""
Backward compatibility shim for usdjpy_regime_bot.
Please use `forex_regime_bot` directly for new code.
"""

from forex_regime_bot import (
    ForexRegimeBot,
    USDJPYRegimeBot,
    run_bot,
    is_forex_market_open,
    send_notification,
)

__all__ = [
    "ForexRegimeBot",
    "USDJPYRegimeBot",
    "run_bot",
    "is_forex_market_open",
    "send_notification",
]

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="paper", choices=["paper", "live"])
    args = parser.parse_args()
    run_bot(args.mode)
