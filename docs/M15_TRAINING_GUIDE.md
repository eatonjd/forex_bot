# Training M15 Intraday Forex Bot - Complete Guide

## 🎯 **Goal**

Train a faster intraday trading bot using 15-minute (M15) candles for more frequent trading opportunities.

**Current Bot**: H1 (hourly) swing trading, 2-5 trades/day  
**New Bot**: M15 intraday trading, 5-15 trades/day  

---

## 📊 **Why M15? (The Sweet Spot)**

| Timeframe | Trades/Day | Noise Level | Spread Impact | Recommended |
|-----------|------------|-------------|---------------|-------------|
| M1 | 50+ | Very High | Killer | ❌ |
| M5 | 20-30 | High | High | 🟡 |
| **M15** | **8-15** | **Medium** | **Manageable** | ✅ **Best** |
| H1 (Current) | 2-5 | Low | Low | ✅ |

M15 balances:

- ✅ More trading opportunities than H1
- ✅ Less noise than M1/M5
- ✅ Manageable spread costs
- ✅ Still enough data to learn patterns

---

## 🛠️ **Step 1: Create Training Script**

### **File**: `train_rl_m15.py`

```python
#!/usr/bin/env python3
"""
Train RL model on M15 (15-minute) data for intraday forex trading.

Key differences from H1 version:
- M15 granularity (60 minutes / 15 = 4x more data)
- Shorter training window (3 months vs 9 months)
- Adjusted reward for faster trades
- Different hyperparameters
"""

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import gymnasium as gym
from gymnasium import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

# Import your feature engineering
from utils.feature_engineering import add_all_features


class M15TradingEnv(gym.Env):
    """
    M15 (15-min) Forex Trading Environment
    
    Optimized for intraday trading:
    - Faster reward decay (intraday positions)
    - Tighter stop losses (10 pips)
    - Quick profit targets (15-20 pips)
    """
    
    def __init__(self, df):
        super().__init__()
        
        self.df = df.reset_index(drop=True)
        self.current_step = 0
        self.position = 0  # 0=neutral, 1=long
        self.entry_price = 0
        self.account_balance = 5000.0
        self.initial_balance = 5000.0
        
        # M15 specific parameters
        self.max_hold_periods = 32  # 8 hours max hold (32 × 15min)
        self.hold_time = 0
        
        # Feature count (25 indicators from feature_engineering)
        n_features = 25
        
        # Observation: features + position + hold_time + balance + unrealized_pl
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, 
            shape=(n_features + 4,), 
            dtype=np.float32
        )
        
        # Actions: 0=HOLD, 1=BUY, 2=SELL
        self.action_space = spaces.Discrete(3)
    
    def reset(self, seed=None):
        super().reset(seed=seed)
        self.current_step = 50  # Start with history
        self.position = 0
        self.entry_price = 0
        self.hold_time = 0
        self.account_balance = self.initial_balance
        return self._get_observation(), {}
    
    def _get_observation(self):
        """Get current market state"""
        # Get features (25 indicators)
        feature_cols = [c for c in self.df.columns 
                       if c not in ['Open', 'High', 'Low', 'Close', 'Volume', 'time']]
        features = self.df.iloc[self.current_step][feature_cols].values.astype(np.float32)
        
        # Add account state
        position_state = np.array([
            self.position,
            self.hold_time / self.max_hold_periods,  # Normalized
            self.account_balance / self.initial_balance,
            self._get_unrealized_pl() / self.initial_balance
        ], dtype=np.float32)
        
        return np.concatenate([features, position_state])
    
    def _get_unrealized_pl(self):
        """Calculate unrealized P/L"""
        if self.position == 0:
            return 0.0
        
        current_price = self.df.iloc[self.current_step]['Close']
        pips = (current_price - self.entry_price) / 0.0001
        # 1000 units = $1 per pip
        return pips * 10.0
    
    def step(self, action):
        current_price = self.df.iloc[self.current_step]['Close']
        reward = 0.0
        
        # Execute action
        if action == 1 and self.position == 0:  # BUY
            self.position = 1
            self.entry_price = current_price
            self.hold_time = 0
            reward -= 0.15  # Spread cost (1.5 pips)
            
        elif action == 2 and self.position == 1:  # SELL (close)
            pips = (current_price - self.entry_price) / 0.0001
            profit = pips * 10.0
            self.account_balance += profit
            
            # M15 specific rewards
            if profit > 0:
                reward = profit / 50.0  # Scale for learning
                # Bonus for quick wins
                if self.hold_time < 8:  # < 2 hours
                    reward *= 1.2
            else:
                reward = profit / 50.0
            
            self.position = 0
            self.entry_price = 0
            self.hold_time = 0
        
        # Holding costs (encourage action)
        if self.position == 1:
            self.hold_time += 1
            
            # Force close if held too long
            if self.hold_time >= self.max_hold_periods:
                pips = (current_price - self.entry_price) / 0.0001
                profit = pips * 10.0
                self.account_balance += profit
                reward = profit / 50.0 - 2.0  # Penalty for timeout
                self.position = 0
                self.entry_price = 0
                self.hold_time = 0
            else:
                # Small penalty for holding (encourage faster trades)
                reward -= 0.01 * (self.hold_time / self.max_hold_periods)
        
        # Move to next step
        self.current_step += 1
        done = self.current_step >= len(self.df) - 1
        truncated = False
        
        return self._get_observation(), reward, done, truncated, {}


def download_m15_data(symbol="EURUSD=X", months=3):
    """
    Download M15 (15-minute) forex data.
    
    Note: Yahoo Finance provides 15-min data for only ~60 days.
    For production, use OANDA historical data.
    """
    print(f"📥 Downloading {months} months of M15 data for {symbol}...")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=months * 30)
    
    # Download 15-min data
    df = yf.download(
        symbol, 
        start=start_date, 
        end=end_date, 
        interval="15m",
        progress=False
    )
    
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    print(f"✅ Downloaded {len(df)} 15-min candles")
    return df


def prepare_m15_features(df):
    """Add technical indicators optimized for M15"""
    print("🔧 Adding M15-optimized features...")
    
    df = df.copy()
    df = df.reset_index()
    df = add_all_features(df)
    
    # Drop NaN from indicators
    df = df.dropna()
    
    print(f"✅ {len(df)} candles ready for training")
    return df


def train_m15_model(
    timesteps=150000,  # More steps for faster timeframe
    save_path="models/ppo_m15_intraday"
):
    """Train PPO model on M15 data"""
    
    print("\n" + "="*60)
    print("TRAINING M15 INTRADAY FOREX BOT")
    print("="*60)
    
    # Step 1: Download data
    df = download_m15_data("EURUSD=X", months=3)
    
    # Step 2: Prepare features
    df = prepare_m15_features(df)
    
    # Step 3: Create environment
    print("\n🏗️  Creating M15 trading environment...")
    env = DummyVecEnv([lambda: M15TradingEnv(df)])
    
    # Step 4: Initialize PPO model
    print("🤖 Initializing PPO model...")
    model = PPO(
        "MlpPolicy",
        env,
        learning_rate=0.0003,
        n_steps=2048,
        batch_size=64,
        n_epochs=10,
        gamma=0.95,  # Faster discount for intraday
        gae_lambda=0.9,
        clip_range=0.2,
        verbose=1,
        device='cpu'
    )
    
    # Step 5: Train
    print(f"\n🎓 Training for {timesteps:,} timesteps...")
    print("This will take ~20-30 minutes...\n")
    
    model.learn(total_timesteps=timesteps)
    
    # Step 6: Save
    print(f"\n💾 Saving model to {save_path}...")
    model.save(save_path)
    
    print("\n" + "="*60)
    print("✅ M15 MODEL TRAINING COMPLETE!")
    print("="*60)
    print(f"\nModel saved: {save_path}.zip")
    print("\nNext steps:")
    print("1. Backtest: python backtest_m15.py")
    print("2. Deploy: Update paper_trading_bot.py to use M15")
    
    return model


if __name__ == "__main__":
    model = train_m15_model(
        timesteps=150000,
        save_path="models/ppo_m15_intraday"
    )
```

---

## 📈 **Step 2: Create M15 Backtest**

### **File**: `backtest_m15.py`

```python
#!/usr/bin/env python3
"""Backtest M15 intraday model"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from stable_baselines3 import PPO
from utils.feature_engineering import add_all_features
from utils.position_manager import PositionManager

# M15 Position Manager config
PM_CONFIG_M15 = {
    "enable_breakeven": True,
    "breakeven_pips": 10.0,  # Faster breakeven
    "breakeven_offset": 3.0,
    "enable_trailing": True,
    "trailing_start_pips": 15.0,  # Tighter trailing
    "trailing_step_pips": 5.0,
    "trailing_distance_pips": 8.0,
    "enable_auto_close": False,
}

def backtest_m15(model_path="models/ppo_m15_intraday"):
    """Backtest M15 strategy"""
    
    print("📊 M15 Intraday Backtest\n")
    
    # Load model
    model = PPO.load(model_path)
    pm = PositionManager(**PM_CONFIG_M15)
    
    # Get test data (last 2 weeks)
    end_date = datetime.now()  
    start_date = end_date - timedelta(days=14)
    
    df = yf.download("EURUSD=X", start=start_date, end=end_date, 
                     interval="15m", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    df = df.reset_index()
    df = add_all_features(df)
    df = df.dropna()
    
    # Backtest
    balance = 5000.0
    position = None
    trades = []
    
    for i in range(50, len(df)):
        current_price = df.iloc[i]['Close']
        
        # Get features
        feature_cols = [c for c in df.columns 
                       if c not in ['Open', 'High', 'Low', 'Close', 'Volume', 'time']]
        features = df.iloc[i][feature_cols].values.astype(np.float32)
        
        pos_state = [0 if position is None else 1, 0, 1.0, 0]
        obs = np.concatenate([features, pos_state])
        
        # Get signal
        action, _ = model.predict(obs, deterministic=True)
        
        # Execute
        if action == 1 and position is None:  # BUY
            position = {
                'entry': current_price,
                'sl': current_price - 0.001,  # 10 pips
                'position_id': f'm15_{i}'
            }
            
        elif position is not None:
            # Check PM
            pips = (current_price - position['entry']) / 0.0001
            profit_usd = pips * 10.0
            
            pm_result = pm.manage_position(
                position_id=position['position_id'],
                symbol='EUR_USD',
                direction='BUY',
                entry_price=position['entry'],
                current_price=current_price,
                current_sl=position['sl'],
                current_profit_usd=profit_usd
            )
            
            if pm_result['action'] == 'close' or action == 2:
                trades.append({
                    'entry': position['entry'],
                    'exit': current_price,
                    'pips': pips,
                    'profit': profit_usd
                })
                balance += profit_usd
                position = None
    
    # Results
    print(f"Total trades: {len(trades)}")
    wins = [t for t in trades if t['profit'] > 0]
    print(f"Win rate: {len(wins)/len(trades)*100:.1f}%")
    print(f"Avg pips: {np.mean([t['pips'] for t in trades]):.1f}")
    print(f"Total profit: ${sum([t['profit'] for t in trades]):.2f}")
    print(f"Final balance: ${balance:.2f}")
    print(f"Return: {(balance/5000-1)*100:.1f}%")
    
    return trades

if __name__ == "__main__":
    backtest_m15()
```

---

## 🚀 **Step 3: Deploy M15 Bot**

### **Option A: Replace H1 Bot**

Update `paper_trading_bot.py`:

```python
# Change these lines:
CHECK_INTERVAL = 60  # Check every 1 minute (not 5)
INITIAL_SL_PIPS = 10  # Tighter stops

# Load M15 model
self.model = PPO.load("models/ppo_m15_intraday")

# Use M15 candles
candles = self.oanda.get_candles(instrument, granularity="M15", count=100)

# Use M15 PM config
PM_CONFIG = {
    "breakeven_pips": 10.0,
    "trailing_start_pips": 15.0,
    # etc...
}
```

### **Option B: Run Both (Dual Strategy)**

Create `paper_trading_bot_m15.py` (copy of original but with M15 settings)

Deploy both:

```bash
# Deploy M15 bot
gcloud run deploy forex-trading-bot-m15 \
  --source . \
  --region us-central1 \
  --memory 1Gi
```

---

## 📋 **Execution Checklist**

### **Phase 1: Training (Today)**

- [ ] Create `train_rl_m15.py`
- [ ] Run training: `python train_rl_m15.py`
- [ ] Wait ~20-30 minutes
- [ ] Verify model saved: `models/ppo_m15_intraday.zip`

### **Phase 2: Backtesting (Same Day)**

- [ ] Create `backtest_m15.py`
- [ ] Run backtest: `python backtest_m15.py`
- [ ] Verify win rate > 60%
- [ ] Verify positive returns

### **Phase 3: Validation (Week 1-2)**

- [ ] If backtest good, create `paper_trading_bot_m15.py`
- [ ] Test locally first
- [ ] Deploy to Cloud Run
- [ ] Monitor for 1-2 weeks

### **Phase 4: Comparison (Week 3-4)**

- [ ] Compare M15 vs H1 performance
- [ ] Choose best performer
- [ ] Scale up winner

---

## ⚠️ **Important Notes**

### **Data Limitations**

- Yahoo Finance: Only 60 days of M15 data
- For production: Use OANDA historical API
- Better: Download 6+ months from OANDA

### **OANDA Historical Data Script**

```python
# utils/download_oanda_m15.py
from oanda_connector import OANDAConnector

oanda = OANDAConnector(environment="practice")
candles = oanda.get_candles("EUR_USD", granularity="M15", count=10000)
# Save to CSV for training
```

### **Expected Results**

- **Trades/Day**: 8-15 (vs 2-5 for H1)
- **Win Rate**: 60-65% (vs 69.7% for H1)  
- **Avg Win**: +12 pips (vs +25 for H1)
- **Spread Cost**: Higher (more trades)
- **Net Result**: Similar or slightly lower than H1

---

## 🎯 **When to Use M15 vs H1**

| Scenario | Use M15 | Use H1 |
|----------|---------|--------|
| Want more action | ✅ | |
| Have time to monitor | ✅ | |
| Low spread broker | ✅ | |
| Maximize total profit | | ✅ |
| Maximize win rate | | ✅ |
| Minimize monitoring | | ✅ |
| Best Sharpe ratio | | ✅ |

**Recommendation**: Train M15, backtest it, but keep H1 as primary unless M15 proves significantly better.

---

## 📞 **Questions to Answer First**

Before training M15:

1. Is H1 bot performing as expected? (Wait 1-2 weeks)
2. Do you want more trades or higher quality?
3. How much time will you monitor?
4. What's your spread on M15 trades?

**Safe approach**: Train M15 now, backtest thoroughly, deploy only if it beats H1.

---

**Saved as reference for future use!** 📝
