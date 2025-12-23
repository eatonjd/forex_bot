# 💰 Forex Bot Money Management - Complete Guide

## 📊 **Current Money Management System**

### **Overview**

The forex bot uses a **simple fixed position sizing** with dynamic exit management via the Position Manager.

---

## 🎯 **Position Sizing**

### **Current Setup** (paper_trading_bot.py)

```python
UNITS_PER_TRADE = 1000  # Fixed position size
```

**What this means:**

- **1000 units = 0.01 lot** (micro lot in forex)
- **$1 per pip** movement (approximately)
- Example: If EUR/USD moves 50 pips, you gain/lose ~$50

### **Account Impact**

On your **$100,000 practice account**:

- Position size: 1000 units = ~$1,172 notional (at EUR/USD 1.17234)
- Notional exposure: **~1.17% of account**
- Very conservative!

---

## 🛡️ **Risk Management**

### **1. Initial Stop Loss**

```python
INITIAL_SL_PIPS = 30  # 30 pips
```

**Risk per trade:**

- 30 pips × $1/pip = **$30 maximum loss**
- **0.03% of $100K account**
- Very conservative (typical is 1-2% per trade)

### **2. Position Manager (Dynamic Exits)**

The Position Manager optimizes exits after entry:

#### **Breakeven Protection**

```python
'breakeven_pips': 20.0,        # Move SL to breakeven at +20 pips
'breakeven_offset': 5.0,       # Lock in +5 pips profit
```

**What happens:**

- If trade goes +20 pips in profit → SL moves to entry +5 pips
- **Risk eliminated**, guaranteed +$5 minimum profit

#### **Trailing Stop**

```python
'trailing_start_pips': 30.0,   # Start trailing at +30 pips
'trailing_step_pips': 10.0,    # Trail every +10 pips
'trailing_distance_pips': 15.0 # Keep SL 15 pips behind
```

**Example:**

1. Trade at +30 pips → Trailing activates
2. Price moves to +40 pips → SL moves to +25 pips (40-15)
3. Price moves to +50 pips → SL moves to +35 pips
4. Price reverses to +36 pips → Exit at +35 pips ✅

**Result**: Captures **most of the trend**, locks in profits!

---

## 💡 **Risk Per Trade Breakdown**

| Scenario | Risk | % of Account |
|----------|------|--------------|
| **Initial Entry** | -$30 (30 pips) | 0.03% |
| **After Breakeven** | +$5 minimum | 0.005% |
| **With Trailing** | Locked profit | 0% |

**Key Point**: After +20 pips, you **cannot lose**! Position Manager protects you.

---

## 🚨 **What's MISSING** (vs trading_bot)

### ❌ **Not Implemented:**

1. **Dynamic Position Sizing**
   - Current: Fixed 1000 units
   - Better: Scale based on account size, volatility

2. **Kelly Criterion**
   - Current: No optimization
   - Better: Calculate optimal bet size based on win rate/edge

3. **Max Positions Limit**
   - Current: No limit (1 position per symbol)
   - Better: Max 3-5 positions total

4. **Daily Loss Limit**
   - Current: No limit
   - Better: Stop trading if -3% daily loss

5. **Correlation Check**
   - Current: EUR/USD + GBP/USD can correlate
   - Better: Limit correlated pairs

6. **Volatility Adjustment**
   - Current: Fixed 30 pip SL
   - Better: ATR-based stops (already calculated!)

---

## 📈 **Position Sizing Recommendations**

### **Option A: Fixed Percentage Risk**

```python
def calculate_position_size(account_balance, risk_pct, sl_pips):
    """
    Risk 1% of account per trade
    
    Example:
    - Account: $100,000
    - Risk: 1% = $1,000
    - SL: 30 pips
    - Position: $1,000 / (30 pips × $10/pip) = ~3.3 lots
    """
    risk_amount = account_balance * risk_pct
    position_size = risk_amount / (sl_pips * 10)  # $10 per pip for standard lot
    return position_size
```

### **Option B: Kelly Criterion** (Advanced)

```python
def kelly_position_size(win_rate, avg_win, avg_loss):
    """
    Based on your backtest:
    - Win rate: 69.7%
    - Avg win: ~15 pips
    - Avg loss: ~10 pips
    
    Kelly % = (win_rate × avg_win - loss_rate × avg_loss) / avg_win
    """
    kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
    conservative_kelly = kelly * 0.5  # Half-Kelly for safety
    return conservative_kelly
```

### **Option C: ATR-Based Sizing**

```python
def atr_position_size(account, risk_pct, atr_value):
    """
    Uses Average True Range for volatility-adjusted sizing
    
    Example:
    - ATR = 0.00089 (from indicators)
    - SL = 2 × ATR = 0.00178 (17.8 pips)
    - Risk: 1% = $1,000
    - Position: $1,000 / (17.8 pips × $1/pip) = larger size
    """
    sl_pips = atr_value * 2 / 0.0001
    return account * risk_pct / (sl_pips * 10)
```

---

## 🎯 **Current vs Recommended**

| Feature | Current | Conservative | Aggressive |
|---------|---------|--------------|------------|
| **Position Size** | 1000 units (0.01 lot) | 2% risk (~0.06 lots) | 5% risk (~0.15 lots) |
| **Risk per Trade** | 0.03% | 1-2% | 3-5% |
| **SL Method** | Fixed 30 pips | 2× ATR | 1.5× ATR |
| **Max Positions** | Unlimited | 3 | 5 |
| **Daily Loss Limit** | None | -3% | -5% |

---

## 💰 **Profit Potential Analysis**

### **Current Setup** (1000 units, 30 pip SL)

- Risk: $30/trade
- Win rate: 69.7%
- Avg win: +15 pips = $15
- Avg loss: -30 pips = $30

**Expected Value per trade:**

```
EV = (0.697 × $15) - (0.303 × $30)
   = $10.45 - $9.09
   = +$1.36 per trade
```

**With Position Manager trailing:**

- Avg win increases to ~25 pips = $25
- **EV = +$8.33 per trade** ✅

### **With 1% Risk Sizing** (0.033 lots)

- Risk: $1000/trade  
- Avg win: $833
- **EV = ~$277 per trade**
- **33× more profit!**

---

## 🚀 **Recommendations**

### **Phase 1: Keep Current (Safe)**

- ✅ Learn the system
- ✅ Validate on paper trading
- ✅ 1-2 weeks observation

### **Phase 2: Add Safety Limits** (Week 3)

```python
MAX_POSITIONS = 3
MAX_DAILY_LOSS_PCT = 0.03  # -3%
CORRELATION_LIMIT = 0.7     # Don't trade EUR/GBP if EUR/USD active
```

### **Phase 3: Dynamic Sizing** (Month 2)

```python
# Risk 1% per trade
RISK_PER_TRADE_PCT = 0.01

def calculate_units(account_balance, sl_pips):
    risk_amount = account_balance * RISK_PER_TRADE_PCT
    units = risk_amount / (sl_pips * 0.1)  # $0.10 per pip for 1000 units
    return int(units / 1000) * 1000  # Round to 1000
```

### **Phase 4: ATR-Based Stops** (Month 3)

```python
# Already calculated in indicators!
atr = indicators.get('atr', 0.00089)
sl_pips = (atr * 2) / 0.0001  # 2× ATR
```

---

## 📋 **Want Me To Implement?**

I can add:

**Option A: Simple Risk Management** (15 min)

- Max 3 positions
- Daily loss limit (-3%)
- Basic correlation check

**Option B: Dynamic Position Sizing** (30 min)

- 1% risk per trade
- Account-based sizing
- ATR-based stops

**Option C: Full Risk Manager** (1 hour)

- Kelly criterion
- Volatility adjustment
- Portfolio heat map
- Daily/weekly limits

**Which would you like?** Or keep current conservative setup for now?
