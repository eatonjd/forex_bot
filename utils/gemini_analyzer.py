#!/usr/bin/env python3
"""
Gemini Market Analyzer

Text-based AI analysis using Google's Gemini API for Smart Money Concepts
and Wyckoff pattern detection. Simplified version without chart images.

Features:
- Text-only analysis (no image uploads, faster, cheaper)
- SMC/Wyckoff pattern recognition
- Multi-timeframe analysis
- Trading signal generation
- Integration with Multi-Symbol Scanner

Author: Forex Bot Team
Created: 2025-12-18
"""

import os
import logging
from typing import Dict, List, Optional
from datetime import datetime

try:
    import google.generativeai as genai

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("google-generativeai not installed. Gemini features disabled.")

logger = logging.getLogger(__name__)


class GeminiMarketAnalyzer:
    """
    AI-powered market analysis using Google Gemini.

    Analyzes price data and provides trading signals based on
    Smart Money Concepts and Wyckoff methodology.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-1.5-flash",
        temperature: float = 0.7,
    ):
        """
        Initialize Gemini Market Analyzer.

        Args:
            api_key: Google Gemini API key (or use GOOGLE_API_KEY env var)
            model_name: Model to use (gemini-1.5-flash or gemini-1.5-pro)
            temperature: Response creativity (0.0-2.0, lower = more deterministic)
        """
        if not GEMINI_AVAILABLE:
            logger.error("google-generativeai not installed")
            self.enabled = False
            return

        # Get API key
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            logger.error("No Gemini API key provided")
            self.enabled = False
            return

        # Configure Gemini
        genai.configure(api_key=self.api_key)

        # Create model
        self.model_name = model_name
        self.model = self._create_model(temperature)
        self.enabled = True

        logger.info(f"GeminiMarketAnalyzer initialized with {model_name}")

    def _create_model(self, temperature: float):
        """Create Gemini model with configuration"""

        generation_config = {
            "temperature": temperature,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 2048,
            "response_mime_type": "text/plain",
        }

        system_instruction = """You are an expert forex trader specializing in Smart Money Concepts (SMC) and Wyckoff methodology.

Your task: Analyze price data and provide SHORT, ACTIONABLE trading signals.

ANALYSIS FRAMEWORK:
1. Identify current market phase (Accumulation/Distribution/Markup/Markdown)
2. Detect SMC patterns (Order Blocks, Fair Value Gaps, Liquidity Sweeps)
3. Apply Wyckoff events (Springs, Upthrusts, Tests)
4. Determine bias (BULLISH/BEARISH/NEUTRAL)

OUTPUT FORMAT:
BIAS: [BULLISH/BEARISH/NEUTRAL]
CONFIDENCE: [0-100]%
SIGNAL: [BUY/SELL/HOLD]
ENTRY: [price]
STOP_LOSS: [price]
TAKE_PROFIT: [price]
REASONING: [2-3 sentences maximum]

Keep responses CONCISE. No lengthy explanations."""

        return genai.GenerativeModel(
            model_name=self.model_name,
            generation_config=generation_config,
            system_instruction=system_instruction,
        )

    def analyze_symbol(
        self, symbol: str, price_data: Dict, timeframe: str = "H1"
    ) -> Dict:
        """
        Analyze a single symbol and generate trading signal.

        Args:
            symbol: Trading pair (e.g., "EURUSD")
            price_data: Dict with OHLCV data
                {
                    'open': [float],
                    'high': [float],
                    'low': [float],
                    'close': [float],
                    'volume': [float]
                }
            timeframe: Timeframe being analyzed

        Returns:
            Dict with analysis results
        """
        if not self.enabled:
            return self._get_disabled_response()

        try:
            # Prepare prompt
            prompt = self._create_analysis_prompt(symbol, price_data, timeframe)

            # Get analysis from Gemini
            response = self.model.generate_content(prompt)

            # Parse response
            analysis = self._parse_response(response.text, symbol)

            logger.info(
                f"Gemini analyzed {symbol}: {analysis['signal']} "
                f"(confidence: {analysis['confidence']}%)"
            )

            return analysis

        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            return self._get_error_response(symbol, str(e))

    def _create_analysis_prompt(
        self, symbol: str, price_data: Dict, timeframe: str
    ) -> str:
        """Create analysis prompt from price data"""

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

RECENT PRICE ACTION (last {n_candles} candles):
"""

        # Add recent candles
        for i, candle in enumerate(recent_candles[-10:], 1):
            direction = "🟢" if candle["close"] > candle["open"] else "🔴"
            prompt += f"{i}. {direction} O:{candle['open']:.5f} H:{candle['high']:.5f} L:{candle['low']:.5f} C:{candle['close']:.5f}\n"

        prompt += "\nProvide your analysis in the specified format."

        return prompt

    def _parse_response(self, response_text: str, symbol: str) -> Dict:
        """Parse Gemini response into structured format"""

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
                except:
                    pass
            elif line.startswith("SIGNAL:"):
                analysis["signal"] = line.split(":", 1)[1].strip().upper()
            elif line.startswith("ENTRY:"):
                try:
                    analysis["entry"] = float(line.split(":", 1)[1].strip())
                except:
                    pass
            elif line.startswith("STOP_LOSS:") or line.startswith("STOP LOSS:"):
                try:
                    analysis["stop_loss"] = float(line.split(":", 1)[1].strip())
                except:
                    pass
            elif line.startswith("TAKE_PROFIT:") or line.startswith("TAKE PROFIT:"):
                try:
                    analysis["take_profit"] = float(line.split(":", 1)[1].strip())
                except:
                    pass
            elif line.startswith("REASONING:"):
                analysis["reasoning"] = line.split(":", 1)[1].strip()

        return analysis

    def _get_disabled_response(self) -> Dict:
        """Return response when Gemini is disabled"""
        return {
            "symbol": "UNKNOWN",
            "timestamp": datetime.now().isoformat(),
            "bias": "NEUTRAL",
            "confidence": 0,
            "signal": "HOLD",
            "entry": 0.0,
            "stop_loss": 0.0,
            "take_profit": 0.0,
            "reasoning": "Gemini analyzer disabled",
            "error": "Gemini not available",
        }

    def _get_error_response(self, symbol: str, error: str) -> Dict:
        """Return response when analysis fails"""
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
        }


# Demo/Testing
if __name__ == "__main__":
    print("🤖 Gemini Market Analyzer - Demo\n")

    # Check if API key is available
    api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        print("⚠️  No GOOGLE_API_KEY environment variable set")
        print("\nTo use Gemini:")
        print("1. Get API key from https://makersuite.google.com/app/apikey")
        print("2. Set environment variable: export GOOGLE_API_KEY='your-key'")
        print("3. Run this script again")
        print("\nFor now, showing mock functionality...\n")

    # Create analyzer
    analyzer = GeminiMarketAnalyzer()

    if not analyzer.enabled:
        print("❌ Gemini analyzer not enabled")
        print("   Install: pip install google-generativeai")
    else:
        print("✅ Gemini analyzer initialized")
        print(f"   Model: {analyzer.model_name}\n")

        # Mock price data
        import random

        price_data = {
            "open": [1.08 + random.uniform(-0.01, 0.01) for _ in range(50)],
            "high": [1.08 + random.uniform(0, 0.02) for _ in range(50)],
            "low": [1.08 + random.uniform(-0.02, 0) for _ in range(50)],
            "close": [1.08 + random.uniform(-0.01, 0.01) for _ in range(50)],
            "volume": [1000 + random.randint(-200, 200) for _ in range(50)],
        }

        print("Analyzing EUR/USD...\n")

        if api_key:
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
        else:
            print("   (Skipping actual API call - no API key)")

    print("\n✅ Demo complete!")
