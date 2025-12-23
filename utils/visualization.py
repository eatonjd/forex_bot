"""
Visualization utilities for the Trading Bot.

Creates charts for training progress, trading results, and comparisons.
"""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from typing import List, Optional, Dict, Any
import os


# Set style for better looking plots
plt.style.use('seaborn-v0_8-darkgrid')


def plot_trading_results(
    df: pd.DataFrame,
    portfolio_values: np.ndarray,
    trades: List[Dict],
    initial_balance: float,
    save_path: Optional[str] = None,
    show: bool = True
) -> None:
    """
    Plot comprehensive trading results.
    
    Args:
        df: DataFrame with price data
        portfolio_values: Array of portfolio values over time
        trades: List of trade dictionaries
        initial_balance: Starting balance for comparison
        save_path: Path to save the figure
        show: Whether to display the plot
    """
    fig, axes = plt.subplots(3, 1, figsize=(14, 12))
    fig.suptitle("Trading Bot Performance", fontsize=16, fontweight='bold')
    
    # Prepare data
    prices = df["Close"].values[:len(portfolio_values)]
    steps = np.arange(len(portfolio_values))
    
    # Calculate buy and hold for comparison
    buy_hold_shares = initial_balance / prices[0]
    buy_hold_values = buy_hold_shares * prices
    
    # ======= Plot 1: Portfolio Value Comparison =======
    ax1 = axes[0]
    ax1.plot(steps, portfolio_values, label="RL Bot", color="#2ecc71", linewidth=2)
    ax1.plot(steps, buy_hold_values, label="Buy & Hold", color="#3498db", linewidth=2, linestyle="--")
    ax1.axhline(y=initial_balance, color="#e74c3c", linestyle=":", alpha=0.7, label="Initial Balance")
    
    ax1.fill_between(steps, portfolio_values, initial_balance, 
                     where=(portfolio_values > initial_balance), 
                     alpha=0.3, color="#2ecc71", label="Profit")
    ax1.fill_between(steps, portfolio_values, initial_balance, 
                     where=(portfolio_values < initial_balance), 
                     alpha=0.3, color="#e74c3c", label="Loss")
    
    ax1.set_ylabel("Portfolio Value ($)", fontsize=12)
    ax1.set_title("Portfolio Value Over Time", fontsize=14)
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)
    
    # Add final return annotation
    final_return = (portfolio_values[-1] - initial_balance) / initial_balance * 100
    bh_return = (buy_hold_values[-1] - initial_balance) / initial_balance * 100
    ax1.annotate(f"Bot: {final_return:+.1f}%", 
                xy=(0.02, 0.95), xycoords='axes fraction',
                fontsize=12, fontweight='bold', color="#2ecc71")
    ax1.annotate(f"B&H: {bh_return:+.1f}%", 
                xy=(0.02, 0.88), xycoords='axes fraction',
                fontsize=12, fontweight='bold', color="#3498db")
    
    # ======= Plot 2: Stock Price with Trade Markers =======
    ax2 = axes[1]
    ax2.plot(steps, prices, color="#34495e", linewidth=1.5, label="Stock Price")
    
    # Plot trade markers
    buy_steps = [t["step"] for t in trades if t["action"] == "BUY"]
    buy_prices = [prices[min(s, len(prices)-1)] for s in buy_steps]
    sell_steps = [t["step"] for t in trades if t["action"] == "SELL"]
    sell_prices = [prices[min(s, len(prices)-1)] for s in sell_steps]
    
    ax2.scatter(buy_steps, buy_prices, marker="^", color="#2ecc71", s=100, 
                label=f"Buy ({len(buy_steps)})", zorder=5, edgecolors='white')
    ax2.scatter(sell_steps, sell_prices, marker="v", color="#e74c3c", s=100, 
                label=f"Sell ({len(sell_steps)})", zorder=5, edgecolors='white')
    
    ax2.set_ylabel("Stock Price ($)", fontsize=12)
    ax2.set_title("Stock Price with Trade Decisions", fontsize=14)
    ax2.legend(loc="upper left")
    ax2.grid(True, alpha=0.3)
    
    # ======= Plot 3: Drawdown =======
    ax3 = axes[2]
    
    # Calculate drawdown
    running_max = np.maximum.accumulate(portfolio_values)
    drawdown = (portfolio_values - running_max) / running_max * 100
    
    ax3.fill_between(steps, drawdown, 0, color="#e74c3c", alpha=0.5)
    ax3.plot(steps, drawdown, color="#c0392b", linewidth=1.5)
    
    ax3.set_xlabel("Trading Steps", fontsize=12)
    ax3.set_ylabel("Drawdown (%)", fontsize=12)
    ax3.set_title(f"Portfolio Drawdown (Max: {drawdown.min():.1f}%)", fontsize=14)
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if save_path:
        os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"📊 Saved plot to {save_path}")
    
    if show:
        plt.show()
    else:
        plt.close()


def plot_training_progress(
    rewards: List[float],
    window: int = 100,
    save_path: Optional[str] = None,
    show: bool = True
) -> None:
    """
    Plot training progress showing reward over episodes.
    
    Args:
        rewards: List of episode rewards
        window: Window size for moving average
        save_path: Path to save the figure
        show: Whether to display the plot
    """
    fig, axes = plt.subplots(2, 1, figsize=(12, 8))
    fig.suptitle("Training Progress", fontsize=16, fontweight='bold')
    
    episodes = np.arange(len(rewards))
    rewards = np.array(rewards)
    
    # ======= Plot 1: Raw Rewards =======
    ax1 = axes[0]
    ax1.plot(episodes, rewards, alpha=0.3, color="#3498db", linewidth=0.5)
    
    # Moving average
    if len(rewards) >= window:
        ma = pd.Series(rewards).rolling(window=window).mean()
        ax1.plot(episodes, ma, color="#2980b9", linewidth=2, label=f"{window}-Episode MA")
    
    ax1.set_ylabel("Episode Reward", fontsize=12)
    ax1.set_title("Episode Rewards", fontsize=14)
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # ======= Plot 2: Cumulative Reward =======
    ax2 = axes[1]
    cumulative = np.cumsum(rewards)
    ax2.plot(episodes, cumulative, color="#2ecc71", linewidth=2)
    ax2.fill_between(episodes, cumulative, 0, 
                     where=(cumulative > 0), alpha=0.3, color="#2ecc71")
    ax2.fill_between(episodes, cumulative, 0, 
                     where=(cumulative < 0), alpha=0.3, color="#e74c3c")
    
    ax2.set_xlabel("Episode", fontsize=12)
    ax2.set_ylabel("Cumulative Reward", fontsize=12)
    ax2.set_title("Cumulative Reward Over Training", fontsize=14)
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if save_path:
        os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"📊 Saved training progress to {save_path}")
    
    if show:
        plt.show()
    else:
        plt.close()


def plot_portfolio_comparison(
    results: Dict[str, np.ndarray],
    initial_balance: float,
    save_path: Optional[str] = None,
    show: bool = True
) -> None:
    """
    Compare multiple portfolio strategies.
    
    Args:
        results: Dictionary mapping strategy name to portfolio values
        initial_balance: Starting balance
        save_path: Path to save the figure
        show: Whether to display the plot
    """
    fig, ax = plt.subplots(figsize=(12, 6))
    
    colors = plt.cm.Set2(np.linspace(0, 1, len(results)))
    
    for (name, values), color in zip(results.items(), colors):
        steps = np.arange(len(values))
        returns = (values[-1] - initial_balance) / initial_balance * 100
        ax.plot(steps, values, label=f"{name} ({returns:+.1f}%)", 
                color=color, linewidth=2)
    
    ax.axhline(y=initial_balance, color="#e74c3c", linestyle=":", 
               alpha=0.7, label="Initial Balance")
    
    ax.set_xlabel("Trading Steps", fontsize=12)
    ax.set_ylabel("Portfolio Value ($)", fontsize=12)
    ax.set_title("Strategy Comparison", fontsize=16, fontweight='bold')
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if save_path:
        os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"📊 Saved comparison to {save_path}")
    
    if show:
        plt.show()
    else:
        plt.close()


def print_performance_metrics(
    portfolio_values: np.ndarray,
    trades: List[Dict],
    initial_balance: float,
    trading_days: int = 252
) -> Dict[str, float]:
    """
    Calculate and print performance metrics.
    
    Args:
        portfolio_values: Array of portfolio values
        trades: List of trade dictionaries
        initial_balance: Starting balance
        trading_days: Number of trading days per year
        
    Returns:
        Dictionary of metrics
    """
    # Calculate returns
    returns = np.diff(portfolio_values) / portfolio_values[:-1]
    total_return = (portfolio_values[-1] - initial_balance) / initial_balance
    
    # Annualized return
    n_periods = len(portfolio_values) - 1
    annualized_return = (1 + total_return) ** (trading_days / n_periods) - 1
    
    # Volatility (annualized)
    volatility = np.std(returns) * np.sqrt(trading_days)
    
    # Sharpe Ratio (assuming risk-free rate of 2%)
    risk_free_rate = 0.02
    excess_return = annualized_return - risk_free_rate
    sharpe_ratio = excess_return / volatility if volatility > 0 else 0
    
    # Maximum Drawdown
    running_max = np.maximum.accumulate(portfolio_values)
    drawdown = (portfolio_values - running_max) / running_max
    max_drawdown = drawdown.min()
    
    # Win rate
    n_trades = len(trades)
    if n_trades > 0:
        # This is a simplified win rate based on trade direction vs price movement
        wins = sum(1 for t in trades if t.get("profitable", True))
        win_rate = wins / n_trades
    else:
        win_rate = 0
    
    metrics = {
        "Total Return": total_return * 100,
        "Annualized Return": annualized_return * 100,
        "Volatility": volatility * 100,
        "Sharpe Ratio": sharpe_ratio,
        "Max Drawdown": max_drawdown * 100,
        "Number of Trades": n_trades,
        "Win Rate": win_rate * 100,
        "Final Value": portfolio_values[-1],
    }
    
    # Print metrics
    print("\n" + "="*50)
    print("📈 PERFORMANCE METRICS")
    print("="*50)
    print(f"💰 Final Portfolio Value: ${metrics['Final Value']:,.2f}")
    print(f"📊 Total Return: {metrics['Total Return']:+.2f}%")
    print(f"📅 Annualized Return: {metrics['Annualized Return']:+.2f}%")
    print(f"📉 Max Drawdown: {metrics['Max Drawdown']:.2f}%")
    print(f"⚡ Volatility: {metrics['Volatility']:.2f}%")
    print(f"🎯 Sharpe Ratio: {metrics['Sharpe Ratio']:.2f}")
    print(f"🔄 Number of Trades: {metrics['Number of Trades']}")
    print("="*50 + "\n")
    
    return metrics
