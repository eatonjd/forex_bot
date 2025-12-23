#!/bin/bash
# Quick Bot Monitor Script

echo "============================================================"
echo "PAPER TRADING BOT MONITOR"
echo "============================================================"
echo ""

# Check if bot is running
if ps aux | grep -q "[p]aper_trading_bot"; then
    echo "✅ Bot Status: RUNNING"
    ps aux | grep "[p]aper_trading_bot" | awk '{print "   PID: " $2 ", Runtime: " $10}'
    echo ""
else
    echo "❌ Bot Status: NOT RUNNING"
    echo ""
    echo "To start:"
    echo "  cd /Users/eatonjd/Github/forex_bot"
    echo "  source forex_env/bin/activate"
    echo "  python paper_trading_bot.py &"
    exit 1
fi

# Check OANDA account
echo "📊 Checking OANDA Account..."
cd /Users/eatonjd/Github/forex_bot
source forex_env/bin/activate
python -c "
from utils.oanda_connector import OANDAConnector
oanda = OANDAConnector(environment='practice')
account = oanda.get_account_summary()
print(f'   Balance: \${account[\"balance\"]:,.2f}')
print(f'   Unrealized P/L: \${account[\"unrealized_pl\"]:,.2f}')
print(f'   Open Positions: {account[\"open_positions\"]}')
print(f'   Open Trades: {account[\"open_trades\"]}')
print()

# Show positions
positions = oanda.get_open_positions()
if positions:
    print('📍 Open Positions:')
    for pos in positions:
        units = pos['long_units'] if pos['long_units'] != 0 else pos['short_units']
        print(f'   {pos[\"instrument\"]}: {units:,.0f} units, P/L: \${pos[\"unrealized_pl\"]:,.2f}')
else:
    print('📍 No open positions')
" 2>/dev/null

echo ""
echo "============================================================"
echo ""
echo "Commands:"
echo "  Stop bot:    pkill -f paper_trading_bot"
echo "  View logs:   tail -f ~/paper_trading.log"
echo "  OANDA dash:  https://fxpractice.oanda.com"
echo ""
echo "============================================================"
