#!/usr/bin/env python3
"""
LLM Benchmark Script

Benchmarks local LLM models for forex trading analysis.
Tests latency, memory usage, and response quality.

Usage:
    python scripts/benchmark_llm.py

Prerequisites:
    brew install ollama
    ollama serve
    ollama pull mistral:7b
    ollama pull llama3:8b
    ollama pull phi3:mini

Author: Forex Bot Team
Created: 2025-12-27
"""

import os
import sys
import time
import json
import random
import psutil
from datetime import datetime
from typing import Dict, List, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def generate_mock_price_data(n_candles: int = 50) -> Dict:
    """Generate mock forex price data."""
    base_price = 1.08
    data = {
        "open": [],
        "high": [],
        "low": [],
        "close": [],
        "volume": [],
    }

    for i in range(n_candles):
        open_price = base_price + random.uniform(-0.01, 0.01)
        close_price = open_price + random.uniform(-0.005, 0.005)
        high_price = max(open_price, close_price) + random.uniform(0, 0.003)
        low_price = min(open_price, close_price) - random.uniform(0, 0.003)

        data["open"].append(open_price)
        data["high"].append(high_price)
        data["low"].append(low_price)
        data["close"].append(close_price)
        data["volume"].append(random.randint(800, 1200))

        base_price = close_price  # Trend continuation

    return data


def check_response_quality(response: Dict) -> Dict:
    """Score the quality of an LLM response."""
    score = 0
    max_score = 6
    issues = []

    # Check required fields
    if response.get("bias") in ["BULLISH", "BEARISH", "NEUTRAL"]:
        score += 1
    else:
        issues.append(f"Invalid bias: {response.get('bias')}")

    if response.get("signal") in ["BUY", "SELL", "HOLD"]:
        score += 1
    else:
        issues.append(f"Invalid signal: {response.get('signal')}")

    confidence = response.get("confidence", 0)
    if 0 <= confidence <= 100:
        score += 1
    else:
        issues.append(f"Invalid confidence: {confidence}")

    if response.get("entry", 0) > 0:
        score += 1
    else:
        issues.append("Missing entry price")

    if response.get("stop_loss", 0) > 0:
        score += 1
    else:
        issues.append("Missing stop loss")

    reasoning = response.get("reasoning", "")
    if len(reasoning) > 20:
        score += 1
    else:
        issues.append("Reasoning too short")

    return {
        "score": score,
        "max_score": max_score,
        "percentage": round(100 * score / max_score, 1),
        "issues": issues,
    }


def benchmark_model(model_name: str, runs: int = 3) -> Optional[Dict]:
    """Benchmark a single Ollama model."""
    from utils.ollama_analyzer import OllamaMarketAnalyzer

    print(f"\n{'=' * 60}")
    print(f"📊 Benchmarking: {model_name}")
    print(f"{'=' * 60}")

    # Create analyzer with no rate limit for benchmarking
    analyzer = OllamaMarketAnalyzer(
        model=model_name,
        rate_limit_seconds=0,  # No rate limit for benchmarking
    )

    if not analyzer.enabled:
        print(f"   ❌ Model not available: {model_name}")
        return None

    results = {
        "model": model_name,
        "runs": runs,
        "latencies": [],
        "quality_scores": [],
        "errors": 0,
    }

    # Get baseline memory
    process = psutil.Process()
    baseline_memory = process.memory_info().rss / 1024 / 1024  # MB

    price_data = generate_mock_price_data()

    for i in range(runs):
        print(f"   Run {i + 1}/{runs}...", end=" ", flush=True)

        try:
            start_time = time.time()
            response = analyzer.analyze_symbol("EUR_USD", price_data, "H1", force=True)
            elapsed = time.time() - start_time

            results["latencies"].append(elapsed)

            # Check quality
            quality = check_response_quality(response)
            results["quality_scores"].append(quality["percentage"])

            print(f"✅ {elapsed:.2f}s, quality: {quality['percentage']}%")

            if quality["issues"]:
                print(f"      Issues: {', '.join(quality['issues'][:2])}")

        except Exception as e:
            print(f"❌ Error: {e}")
            results["errors"] += 1

    # Calculate stats
    if results["latencies"]:
        results["avg_latency"] = sum(results["latencies"]) / len(results["latencies"])
        results["min_latency"] = min(results["latencies"])
        results["max_latency"] = max(results["latencies"])
    else:
        results["avg_latency"] = 0
        results["min_latency"] = 0
        results["max_latency"] = 0

    if results["quality_scores"]:
        results["avg_quality"] = sum(results["quality_scores"]) / len(
            results["quality_scores"]
        )
    else:
        results["avg_quality"] = 0

    # Memory after run
    peak_memory = process.memory_info().rss / 1024 / 1024  # MB
    results["memory_delta_mb"] = peak_memory - baseline_memory

    return results


def print_summary(all_results: List[Dict]):
    """Print comparison summary."""
    print("\n" + "=" * 70)
    print("📈 BENCHMARK SUMMARY")
    print("=" * 70)

    # Sort by quality, then by speed
    sorted_results = sorted(
        [r for r in all_results if r is not None],
        key=lambda x: (-x["avg_quality"], x["avg_latency"]),
    )

    print(f"\n{'Model':<20} {'Avg Latency':<15} {'Quality':<12} {'Errors':<10}")
    print("-" * 60)

    for r in sorted_results:
        print(
            f"{r['model']:<20} "
            f"{r['avg_latency']:.2f}s          "
            f"{r['avg_quality']:.1f}%        "
            f"{r['errors']}"
        )

    print("-" * 60)

    if sorted_results:
        best = sorted_results[0]
        print(f"\n🏆 Recommended: {best['model']}")
        print(f"   Avg latency: {best['avg_latency']:.2f}s")
        print(f"   Quality: {best['avg_quality']:.1f}%")


def check_ollama_available() -> bool:
    """Check if Ollama server is running."""
    try:
        import requests

        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        return response.status_code == 200
    except:
        return False


def list_available_models() -> List[str]:
    """List models available in Ollama."""
    try:
        import requests

        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            return [m.get("name", "") for m in models]
    except:
        pass
    return []


def main():
    print("🦙 LLM Benchmark Tool for Forex Trading")
    print("=" * 60)

    # Check Ollama
    if not check_ollama_available():
        print("\n❌ Ollama server not running!")
        print("\nTo start Ollama:")
        print("   brew install ollama")
        print("   ollama serve")
        print("   ollama pull mistral:7b")
        return

    # List available models
    available = list_available_models()
    print(f"\n📋 Available models: {', '.join(available) or 'None'}")

    if not available:
        print("\n⚠️ No models installed. Try:")
        print("   ollama pull mistral:7b")
        print("   ollama pull llama3:8b")
        print("   ollama pull phi3:mini")
        return

    # Models to benchmark (intersection with available)
    target_models = ["mistral:7b", "llama3:8b", "phi3:mini", "gemma:7b"]
    models_to_test = [m for m in target_models if any(m in a for a in available)]

    # Also test any available models not in our list
    for m in available:
        if m not in models_to_test and not any(t in m for t in target_models):
            models_to_test.append(m)

    if not models_to_test:
        # Fall back to first available model
        models_to_test = available[:1]

    print(f"\n🎯 Will benchmark: {', '.join(models_to_test)}")

    # Run benchmarks
    all_results = []
    for model in models_to_test:
        result = benchmark_model(model, runs=3)
        if result:
            all_results.append(result)

    # Print summary
    print_summary(all_results)

    # Save results
    results_file = "benchmark_results.json"
    with open(results_file, "w") as f:
        json.dump(
            {
                "timestamp": datetime.now().isoformat(),
                "results": all_results,
            },
            f,
            indent=2,
        )

    print(f"\n💾 Results saved to: {results_file}")


if __name__ == "__main__":
    main()
