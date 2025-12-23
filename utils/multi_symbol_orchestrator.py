#!/usr/bin/env python3
"""
Multi-Symbol Orchestrator

Parallel analysis and trading across multiple currency pairs and timeframes.
Based on rapid-fire multi-symbol scanning from Bot-ForexMT5.

Features:
- Parallel symbol/timeframe scanning using ThreadPoolExecutor
- Global position limits (max total positions)
- Per-symbol position limits (max positions per pair)
- Rapid-fire mode for high-frequency scanning
- Opportunity scoring and prioritization
- Position tracking and management

Author: Forex Bot Team
Created: 2025-12-18
"""

import logging
from typing import Dict, List, Optional, Tuple, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
import threading

logger = logging.getLogger(__name__)


@dataclass
class TradingSignal:
    """Trading signal from analysis"""

    symbol: str
    timeframe: str
    action: str  # 'BUY', 'SELL', 'HOLD'
    strength: float  # 0.0 to 1.0
    entry_price: float
    stop_loss: float
    take_profit: float
    timestamp: datetime
    confidence: float = 0.0
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class MultiSymbolOrchestrator:
    """
    Orchestrate trading across multiple symbols and timeframes.

    Enables rapid-fire scanning with position limit enforcement
    and parallel analysis for better opportunity discovery.
    """

    def __init__(
        self,
        symbols: List[str],
        timeframes: List[str] = None,
        max_total_positions: int = 10,
        max_positions_per_symbol: int = 3,
        rapid_fire_mode: bool = False,
        max_workers: int = 4,
    ):
        """
        Initialize Multi-Symbol Orchestrator.

        Args:
            symbols: List of symbols to trade (e.g., ['EURUSD', 'GBPUSD'])
            timeframes: List of timeframes to analyze (e.g., ['M5', 'M15', 'H1'])
            max_total_positions: Maximum total open positions across all symbols
            max_positions_per_symbol: Maximum positions per individual symbol
            rapid_fire_mode: Enable high-frequency scanning (more aggressive)
            max_workers: Maximum parallel workers for analysis
        """
        self.symbols = symbols
        self.timeframes = timeframes or ["M15"]  # Default to 15-minute
        self.max_total = max_total_positions
        self.max_per_symbol = max_positions_per_symbol
        self.rapid_fire = rapid_fire_mode
        self.max_workers = max_workers

        # Track open positions
        self.open_positions: Dict[str, List[Dict]] = {}
        self.position_lock = threading.Lock()

        # Analysis function registry
        self.analyzers: List[Callable] = []

        logger.info(
            f"MultiSymbolOrchestrator initialized: "
            f"{len(symbols)} symbols × {len(self.timeframes)} timeframes, "
            f"max_total={max_total_positions}, "
            f"max_per_symbol={max_positions_per_symbol}, "
            f"rapid_fire={rapid_fire_mode}"
        )

    def register_analyzer(self, analyzer_func: Callable):
        """
        Register an analysis function.

        Args:
            analyzer_func: Function that takes (symbol, timeframe, data)
                         and returns TradingSignal
        """
        self.analyzers.append(analyzer_func)
        logger.info(f"Registered analyzer: {analyzer_func.__name__}")

    def scan_opportunities(
        self, data_provider: Optional[Callable] = None
    ) -> List[TradingSignal]:
        """
        Scan all symbol/timeframe combinations for trading opportunities.

        Args:
            data_provider: Optional function to fetch market data
                         (symbol, timeframe) -> market_data

        Returns:
            List of TradingSignals sorted by strength
        """
        if not self.analyzers:
            logger.warning("No analyzers registered")
            return []

        # Generate all symbol/timeframe combinations
        combinations = [
            (symbol, timeframe)
            for symbol in self.symbols
            for timeframe in self.timeframes
            if self._can_open_position(symbol)
        ]

        if not combinations:
            logger.info("No valid combinations (position limits reached)")
            return []

        logger.info(
            f"Scanning {len(combinations)} combinations with {self.max_workers} workers..."
        )

        signals = []

        # Parallel analysis
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit analysis tasks
            futures = {}
            for symbol, timeframe in combinations:
                future = executor.submit(
                    self._analyze_combination, symbol, timeframe, data_provider
                )
                futures[future] = (symbol, timeframe)

            # Collect results
            for future in as_completed(futures):
                symbol, timeframe = futures[future]
                try:
                    signal = future.result()
                    if signal and signal.action != "HOLD":
                        signals.append(signal)
                        logger.debug(
                            f"{symbol}/{timeframe}: {signal.action} "
                            f"(strength={signal.strength:.2f})"
                        )
                except Exception as e:
                    logger.error(f"Error analyzing {symbol}/{timeframe}: {e}")

        # Sort by strength (highest first)
        signals.sort(key=lambda s: s.strength, reverse=True)

        logger.info(
            f"Scan complete: Found {len(signals)} signals "
            f"from {len(combinations)} combinations"
        )

        return signals

    def get_top_opportunities(
        self, n: int = 5, data_provider: Optional[Callable] = None
    ) -> List[TradingSignal]:
        """
        Get top N trading opportunities.

        Args:
            n: Number of top opportunities to return
            data_provider: Optional data provider function

        Returns:
            List of top N signals
        """
        signals = self.scan_opportunities(data_provider)
        return signals[:n]

    def _analyze_combination(
        self, symbol: str, timeframe: str, data_provider: Optional[Callable] = None
    ) -> Optional[TradingSignal]:
        """
        Analyze a single symbol/timeframe combination.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            data_provider: Optional data provider

        Returns:
            TradingSignal or None
        """
        # Fetch market data if provider available
        market_data = None
        if data_provider:
            try:
                market_data = data_provider(symbol, timeframe)
            except Exception as e:
                logger.error(f"Error fetching data for {symbol}/{timeframe}: {e}")
                return None

        # Run all analyzers and aggregate signals
        analyzer_signals = []
        for analyzer in self.analyzers:
            try:
                signal = analyzer(symbol, timeframe, market_data)
                if signal:
                    analyzer_signals.append(signal)
            except Exception as e:
                logger.error(
                    f"Analyzer {analyzer.__name__} failed for {symbol}/{timeframe}: {e}"
                )

        if not analyzer_signals:
            return None

        # Aggregate signals (simple averaging for now)
        return self._aggregate_signals(analyzer_signals)

    def _aggregate_signals(self, signals: List[TradingSignal]) -> TradingSignal:
        """
        Aggregate multiple signals into one.

        Args:
            signals: List of TradingSignals

        Returns:
            Aggregated TradingSignal
        """
        if not signals:
            return None

        if len(signals) == 1:
            return signals[0]

        # Count votes for each action
        buy_votes = sum(1 for s in signals if s.action == "BUY")
        sell_votes = sum(1 for s in signals if s.action == "SELL")

        # Determine consensus action
        if buy_votes > sell_votes:
            action = "BUY"
            strength = buy_votes / len(signals)
        elif sell_votes > buy_votes:
            action = "SELL"
            strength = sell_votes / len(signals)
        else:
            action = "HOLD"
            strength = 0.5

        # Average prices
        avg_entry = sum(s.entry_price for s in signals) / len(signals)
        avg_sl = sum(s.stop_loss for s in signals) / len(signals)
        avg_tp = sum(s.take_profit for s in signals) / len(signals)
        avg_confidence = sum(s.confidence for s in signals) / len(signals)

        return TradingSignal(
            symbol=signals[0].symbol,
            timeframe=signals[0].timeframe,
            action=action,
            strength=strength,
            entry_price=avg_entry,
            stop_loss=avg_sl,
            take_profit=avg_tp,
            timestamp=datetime.now(),
            confidence=avg_confidence,
            metadata={"num_analyzers": len(signals)},
        )

    def _can_open_position(self, symbol: str) -> bool:
        """
        Check if we can open a new position for this symbol.

        Args:
            symbol: Trading symbol

        Returns:
            True if position can be opened
        """
        with self.position_lock:
            # Check global limit
            total_positions = sum(
                len(positions) for positions in self.open_positions.values()
            )
            if total_positions >= self.max_total:
                logger.debug(
                    f"Global position limit reached ({total_positions}/{self.max_total})"
                )
                return False

            # Check per-symbol limit
            symbol_positions = len(self.open_positions.get(symbol, []))
            if symbol_positions >= self.max_per_symbol:
                logger.debug(
                    f"{symbol}: Per-symbol limit reached "
                    f"({symbol_positions}/{self.max_per_symbol})"
                )
                return False

            return True

    def add_position(self, symbol: str, position_data: Dict):
        """
        Track a new open position.

        Args:
            symbol: Trading symbol
            position_data: Position information
        """
        with self.position_lock:
            if symbol not in self.open_positions:
                self.open_positions[symbol] = []
            self.open_positions[symbol].append(position_data)

            total = sum(len(p) for p in self.open_positions.values())
            logger.info(
                f"Position opened: {symbol} "
                f"(symbol: {len(self.open_positions[symbol])}/{self.max_per_symbol}, "
                f"total: {total}/{self.max_total})"
            )

    def remove_position(self, symbol: str, position_id: str):
        """
        Remove a closed position from tracking.

        Args:
            symbol: Trading symbol
            position_id: Position identifier
        """
        with self.position_lock:
            if symbol in self.open_positions:
                self.open_positions[symbol] = [
                    p for p in self.open_positions[symbol] if p.get("id") != position_id
                ]
                if not self.open_positions[symbol]:
                    del self.open_positions[symbol]

                total = sum(len(p) for p in self.open_positions.values())
                logger.info(
                    f"Position closed: {symbol} (total: {total}/{self.max_total})"
                )

    def get_position_summary(self) -> Dict:
        """
        Get summary of current positions.

        Returns:
            Dict with position statistics
        """
        with self.position_lock:
            total_positions = sum(
                len(positions) for positions in self.open_positions.values()
            )

            return {
                "total_positions": total_positions,
                "symbol_count": len(self.open_positions),
                "positions_by_symbol": {
                    symbol: len(positions)
                    for symbol, positions in self.open_positions.items()
                },
                "capacity_total": f"{total_positions}/{self.max_total}",
                "available_slots": self.max_total - total_positions,
            }


# Demo/testing
if __name__ == "__main__":
    import random

    print("🔄 Multi-Symbol Orchestrator - Demo\n")

    # Sample analyzer function
    def trend_analyzer(symbol: str, timeframe: str, data) -> TradingSignal:
        """Simple trend analyzer (mock)"""
        # Simulate analysis with random trends
        trend = random.choice(["BUY", "SELL", "HOLD"])

        if trend == "HOLD":
            return None

        base_price = random.uniform(1.05, 1.15)

        return TradingSignal(
            symbol=symbol,
            timeframe=timeframe,
            action=trend,
            strength=random.uniform(0.6, 1.0),
            entry_price=base_price,
            stop_loss=base_price * (0.98 if trend == "BUY" else 1.02),
            take_profit=base_price * (1.03 if trend == "BUY" else 0.97),
            timestamp=datetime.now(),
            confidence=random.uniform(0.7, 0.95),
        )

    def momentum_analyzer(symbol: str, timeframe: str, data) -> TradingSignal:
        """Simple momentum analyzer (mock)"""
        momentum = random.choice(["BUY", "SELL", "HOLD"])

        if momentum == "HOLD":
            return None

        base_price = random.uniform(1.05, 1.15)

        return TradingSignal(
            symbol=symbol,
            timeframe=timeframe,
            action=momentum,
            strength=random.uniform(0.5, 0.9),
            entry_price=base_price,
            stop_loss=base_price * (0.985 if momentum == "BUY" else 1.015),
            take_profit=base_price * (1.025 if momentum == "BUY" else 0.975),
            timestamp=datetime.now(),
            confidence=random.uniform(0.6, 0.9),
        )

    # Initialize orchestrator
    orchestrator = MultiSymbolOrchestrator(
        symbols=["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"],
        timeframes=["M5", "M15", "H1"],
        max_total_positions=10,
        max_positions_per_symbol=2,
        rapid_fire_mode=True,
        max_workers=4,
    )

    # Register analyzers
    orchestrator.register_analyzer(trend_analyzer)
    orchestrator.register_analyzer(momentum_analyzer)

    print(f"Symbols: {len(orchestrator.symbols)}")
    print(f"Timeframes: {orchestrator.timeframes}")
    print(
        f"Total combinations: {len(orchestrator.symbols) * len(orchestrator.timeframes)}"
    )
    print(f"Max workers: {orchestrator.max_workers}\n")

    # Scan for opportunities
    print("Scanning for trading opportunities...\n")
    signals = orchestrator.scan_opportunities()

    print(f"✅ Found {len(signals)} signals\n")

    # Show top 5 opportunities
    print("Top 5 Opportunities:")
    for i, signal in enumerate(signals[:5], 1):
        print(f"\n{i}. {signal.symbol} ({signal.timeframe})")
        print(f"   Action: {signal.action}")
        print(f"   Strength: {signal.strength:.2f}")
        print(f"   Entry: {signal.entry_price:.5f}")
        print(f"   SL: {signal.stop_loss:.5f}")
        print(f"   TP: {signal.take_profit:.5f}")
        print(f"   Confidence: {signal.confidence:.1%}")

    # Simulate opening positions
    print("\n\nSimulating position management...\n")
    for signal in signals[:3]:
        orchestrator.add_position(
            signal.symbol,
            {
                "id": f"pos_{signal.symbol}_{signal.timestamp.timestamp()}",
                "entry": signal.entry_price,
                "sl": signal.stop_loss,
                "tp": signal.take_profit,
            },
        )

    # Show position summary
    summary = orchestrator.get_position_summary()
    print("\n📊 Position Summary:")
    print(f"   Total Positions: {summary['capacity_total']}")
    print(f"   Available Slots: {summary['available_slots']}")
    print(f"   Symbols Traded: {summary['symbol_count']}")
    print(f"   Per Symbol: {summary['positions_by_symbol']}")

    print("\n✅ Demo complete!")
