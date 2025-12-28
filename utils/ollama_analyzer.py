#!/usr/bin/env python3
"""
Ollama Market Analyzer

Local LLM-based market analysis using Ollama for Smart Money Concepts
and Wyckoff pattern detection. Zero API cost alternative to Gemini.

Features:
- Local inference (no API costs)
- Same interface as GeminiMarketAnalyzer
- Rate limiting and caching
- Works with Mistral, Llama, Phi-3, etc.

Author: Forex Bot Team
Created: 2025-12-27
"""

import os
import time
import logging
import json
from typing import Dict, Optional
from datetime import datetime

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logging.warning("requests not installed. Ollama features disabled.")

logger = logging.getLogger(__name__)


class OllamaMarketAnalyzer:
    """
    Local LLM-powered market analysis using Ollama.

    Analyzes price data and provides trading signals based on
    Smart Money Concepts and Wyckoff methodology.
    """

    SYSTEM_PROMPT = """You are an expert forex trader specializing in Smart Money Concepts (SMC) and Wyckoff methodology.

Your task: Analyze price data and provide SHORT, ACTIONABLE trading signals.

ANALYSIS FRAMEWORK:
1. Identify current market phase (Accumulation/Distribution/Markup/Markdown)
2. Detect SMC patterns (Order Blocks, Fair Value Gaps, Liquidity Sweeps)
3. Apply Wyckoff events (Springs, Upthrusts, Tests)
4. Determine bias (BULLISH/BEARISH/NEUTRAL)

OUTPUT FORMAT (use exactly this format):
BIAS: [BULLISH/BEARISH/NEUTRAL]
CONFIDENCE: [0-100]%
SIGNAL: [BUY/SELL/HOLD]
ENTRY: [price]
STOP_LOSS: [price]
TAKE_PROFIT: [price]
REASONING: [2-3 sentences maximum]

Keep responses CONCISE. No lengthy explanations."""

    def __init__(
        self,
        model: str = "mistral:7b",
        host: str = "http://localhost:11434",
        timeout: int = 30,
        temperature: float = 0.7,
        rate_limit_seconds: int = 3600,
    ):
        """
        Initialize Ollama Market Analyzer.

        Args:
            model: Ollama model name (e.g., mistral:7b, llama3:8b)
            host: Ollama server URL
            timeout: Request timeout in seconds
            temperature: Response creativity (0.0-2.0)
            rate_limit_seconds: Minimum seconds between API calls per symbol
        """
        # Rate limiting
        self.rate_limit_seconds = rate_limit_seconds
        self._last_call_times: Dict[str, float] = {}
        self._cached_results: Dict[str, Dict] = {}

        if not REQUESTS_AVAILABLE:
            logger.error("requests library not installed")
            self.enabled = False
            return

        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.temperature = temperature

        # Check if Ollama is running
        self.enabled = self._check_connection()

        if self.enabled:
            logger.info(
                f"OllamaMarketAnalyzer initialized with {model} (rate limit: {rate_limit_seconds}s)"
            )
        else:
            logger.warning("Ollama server not available")

    def _check_connection(self) -> bool:
        """Check if Ollama server is running and model is available."""
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]

                # Check if our model is available
                if any(self.model in name for name in model_names):
                    return True
                else:
                    logger.warning(
                        f"Model {self.model} not found. Available: {model_names}"
                    )
                    # Still return True - model might be pulled on first use
                    return True
            return False
        except Exception as e:
            logger.debug(f"Ollama connection check failed: {e}")
            return False

    def can_analyze(self, symbol: str) -> bool:
        """Check if we can analyze this symbol (rate limit check)."""
        if symbol not in self._last_call_times:
            return True

        elapsed = time.time() - self._last_call_times[symbol]
        return elapsed >= self.rate_limit_seconds

    def get_cached_result(self, symbol: str) -> Optional[Dict]:
        """Get cached result for a symbol if available."""
        return self._cached_results.get(symbol)

    def seconds_until_available(self, symbol: str) -> int:
        """Get seconds until we can analyze this symbol again."""
        if symbol not in self._last_call_times:
            return 0

        elapsed = time.time() - self._last_call_times[symbol]
        remaining = self.rate_limit_seconds - elapsed
        return max(0, int(remaining))

    def analyze_symbol(
        self, symbol: str, price_data: Dict, timeframe: str = "H1", force: bool = False
    ) -> Dict:
        """
        Analyze a single symbol and generate trading signal.

        Args:
            symbol: Trading pair (e.g., "EURUSD")
            price_data: Dict with OHLCV data
            timeframe: Timeframe being analyzed
            force: If True, bypass rate limiting

        Returns:
            Dict with analysis results
        """
        if not self.enabled:
            return self._get_disabled_response()

        # Check rate limit
        if not force and not self.can_analyze(symbol):
            cached = self.get_cached_result(symbol)
            if cached:
                remaining = self.seconds_until_available(symbol)
                logger.info(
                    f"Rate limited for {symbol}, returning cached result "
                    f"(next call in {remaining}s)"
                )
                cached["from_cache"] = True
                return cached
            else:
                return self._get_rate_limited_response(symbol)

        try:
            # Prepare prompt
            prompt = self._create_analysis_prompt(symbol, price_data, timeframe)

            # Get analysis from Ollama
            response = self._generate(prompt)

            # Parse response
            analysis = self._parse_response(response, symbol)
            analysis["from_cache"] = False
            analysis["provider"] = "ollama"
            analysis["model"] = self.model

            # Update rate limit tracking
            self._last_call_times[symbol] = time.time()
            self._cached_results[symbol] = analysis

            logger.info(
                f"Ollama analyzed {symbol}: {analysis['signal']} "
                f"(confidence: {analysis['confidence']}%)"
            )

            return analysis

        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            return self._get_error_response(symbol, str(e))

    def _generate(self, prompt: str) -> str:
        """Generate response from Ollama."""
        url = f"{self.host}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": self.SYSTEM_PROMPT,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": 500,  # Limit output tokens
            },
        }

        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()

        result = response.json()
        return result.get("response", "")

    def _create_analysis_prompt(
        self, symbol: str, price_data: Dict, timeframe: str
    ) -> str:
        """Create analysis prompt from price data."""
        # Get recent candles (last 20)
        recent_candles = []
        n_candles = min(20, len(price_data.get("close", [])))

        for i in range(-n_candles, 0):
            candle = {
                "open": price_data["open"][i],
                "high": price_data["high"][i],
                "low": price_data["low"][i],
                "close": price_data["close"][i],
                "volume": price_data.get("volume", [0] * len(price_data["close"]))[i],
            }
            recent_candles.append(candle)

        # Calculate some basic stats
        current_price = price_data["close"][-1]
        prev_close = price_data["close"][-2]
        high_20 = max(price_data["high"][-20:])
        low_20 = min(price_data["low"][-20:])

        prompt = f"""Analyze {symbol} on {timeframe} timeframe.

CURRENT DATA:
- Current Price: {current_price:.5f}
- Previous Close: {prev_close:.5f}
- 20-Period High: {high_20:.5f}
- 20-Period Low: {low_20:.5f}

RECENT PRICE ACTION (last {min(10, n_candles)} candles):
"""

        # Add recent candles
        for i, candle in enumerate(recent_candles[-10:], 1):
            direction = "🟢" if candle["close"] > candle["open"] else "🔴"
            prompt += f"{i}. {direction} O:{candle['open']:.5f} H:{candle['high']:.5f} L:{candle['low']:.5f} C:{candle['close']:.5f}\n"

        prompt += "\nProvide your analysis in the specified format."

        return prompt

    def _parse_response(self, response_text: str, symbol: str) -> Dict:
        """Parse Ollama response into structured format."""
        # Default values
        analysis = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "bias": "NEUTRAL",
            "confidence": 50,
            "signal": "HOLD",
            "entry": 0.0,
            "stop_loss": 0.0,
            "take_profit": 0.0,
            "reasoning": "No clear signal",
            "raw_response": response_text,
        }

        # Parse response (simple text parsing)
        lines = response_text.split("\n")

        for line in lines:
            line = line.strip()

            if line.startswith("BIAS:"):
                analysis["bias"] = line.split(":", 1)[1].strip().upper()
            elif line.startswith("CONFIDENCE:"):
                try:
                    conf_str = line.split(":", 1)[1].strip().rstrip("%")
                    analysis["confidence"] = int(conf_str)
                except ValueError:
                    pass
            elif line.startswith("SIGNAL:"):
                analysis["signal"] = line.split(":", 1)[1].strip().upper()
            elif line.startswith("ENTRY:"):
                try:
                    analysis["entry"] = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line.startswith("STOP_LOSS:") or line.startswith("STOP LOSS:"):
                try:
                    analysis["stop_loss"] = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line.startswith("TAKE_PROFIT:") or line.startswith("TAKE PROFIT:"):
                try:
                    analysis["take_profit"] = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line.startswith("REASONING:"):
                analysis["reasoning"] = line.split(":", 1)[1].strip()

        return analysis

    def _get_disabled_response(self) -> Dict:
        """Return response when Ollama is disabled."""
        return {
            "symbol": "UNKNOWN",
            "timestamp": datetime.now().isoformat(),
            "bias": "NEUTRAL",
            "confidence": 0,
            "signal": "HOLD",
            "entry": 0.0,
            "stop_loss": 0.0,
            "take_profit": 0.0,
            "reasoning": "Ollama analyzer disabled",
            "error": "Ollama not available",
            "provider": "ollama",
        }

    def _get_rate_limited_response(self, symbol: str) -> Dict:
        """Return response when rate limited with no cache."""
        return {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "bias": "NEUTRAL",
            "confidence": 0,
            "signal": "HOLD",
            "entry": 0.0,
            "stop_loss": 0.0,
            "take_profit": 0.0,
            "reasoning": "Rate limited, no cached result available",
            "error": "Rate limited",
            "from_cache": False,
            "provider": "ollama",
        }

    def _get_error_response(self, symbol: str, error: str) -> Dict:
        """Return response when analysis fails."""
        return {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "bias": "NEUTRAL",
            "confidence": 0,
            "signal": "HOLD",
            "entry": 0.0,
            "stop_loss": 0.0,
            "take_profit": 0.0,
            "reasoning": "Analysis failed",
            "error": error,
            "provider": "ollama",
        }


# Demo/Testing
if __name__ == "__main__":
    print("🦙 Ollama Market Analyzer - Demo\n")

    # Create analyzer
    analyzer = OllamaMarketAnalyzer()

    if not analyzer.enabled:
        print("❌ Ollama analyzer not enabled")
        print("   Install Ollama: brew install ollama")
        print("   Start server: ollama serve")
        print("   Pull model: ollama pull mistral:7b")
    else:
        print("✅ Ollama analyzer initialized")
        print(f"   Model: {analyzer.model}\n")

        # Mock price data
        import random

        price_data = {
            "open": [1.08 + random.uniform(-0.01, 0.01) for _ in range(50)],
            "high": [1.08 + random.uniform(0, 0.02) for _ in range(50)],
            "low": [1.08 + random.uniform(-0.02, 0) for _ in range(50)],
            "close": [1.08 + random.uniform(-0.01, 0.01) for _ in range(50)],
            "volume": [1000 + random.randint(-200, 200) for _ in range(50)],
        }

        print("Analyzing EUR/USD (this may take 5-10 seconds)...\n")

        # Real analysis
        result = analyzer.analyze_symbol("EURUSD", price_data, "H1")

        print("📊 Analysis Results:")
        print(f"   Bias: {result['bias']}")
        print(f"   Signal: {result['signal']}")
        print(f"   Confidence: {result['confidence']}%")
        print(f"   Entry: {result['entry']:.5f}")
        print(f"   Stop Loss: {result['stop_loss']:.5f}")
        print(f"   Take Profit: {result['take_profit']:.5f}")
        print(f"   Reasoning: {result['reasoning']}")

    print("\n✅ Demo complete!")
