#!/usr/bin/env python3
"""
News Sentiment Analysis Module.

Fetches financial news and analyzes sentiment to gauge market mood.
Uses multiple sources and provides a composite sentiment score.

Sentiment Scale:
- -1.0 to -0.5: Very Bearish
- -0.5 to -0.2: Bearish
- -0.2 to +0.2: Neutral
- +0.2 to +0.5: Bullish
- +0.5 to +1.0: Very Bullish
"""

import os
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import json

import numpy as np

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


@dataclass
class NewsItem:
    """Represents a single news item."""
    title: str
    source: str
    timestamp: datetime
    sentiment: float = 0.0
    relevance: float = 1.0


class SentimentAnalyzer:
    """
    Analyzes sentiment from financial news headlines.
    
    Uses keyword-based analysis with financial-specific vocabulary.
    For production, consider using a proper NLP model like FinBERT.
    """
    
    # Financial sentiment keywords
    BULLISH_WORDS = {
        # Strong bullish
        "surge": 2.0, "soar": 2.0, "skyrocket": 2.0, "boom": 2.0, "rally": 1.5,
        "breakthrough": 1.5, "record high": 2.0, "all-time high": 2.0,
        
        # Moderate bullish
        "gain": 1.0, "rise": 1.0, "climb": 1.0, "advance": 1.0, "growth": 1.0,
        "beat": 1.0, "exceed": 1.0, "outperform": 1.0, "upgrade": 1.5,
        "bullish": 1.5, "optimistic": 1.0, "positive": 0.8, "strong": 0.8,
        "recovery": 1.0, "rebound": 1.0, "upbeat": 1.0, "momentum": 0.8,
        
        # Mild bullish
        "buy": 0.5, "opportunity": 0.5, "potential": 0.5, "promising": 0.5,
        "stabilize": 0.3, "support": 0.3, "confidence": 0.5,
    }
    
    BEARISH_WORDS = {
        # Strong bearish
        "crash": -2.0, "plunge": -2.0, "collapse": -2.0, "crisis": -2.0,
        "recession": -2.0, "panic": -2.0, "meltdown": -2.0,
        
        # Moderate bearish
        "fall": -1.0, "drop": -1.0, "decline": -1.0, "sink": -1.0,
        "miss": -1.0, "disappoint": -1.0, "underperform": -1.0, "downgrade": -1.5,
        "bearish": -1.5, "pessimistic": -1.0, "negative": -0.8, "weak": -0.8,
        "sell-off": -1.5, "selloff": -1.5, "tumble": -1.5, "slump": -1.5,
        
        # Mild bearish
        "sell": -0.5, "risk": -0.5, "concern": -0.5, "uncertainty": -0.5,
        "volatile": -0.3, "pressure": -0.3, "warning": -0.5, "caution": -0.3,
        "fear": -0.8, "worried": -0.5, "trouble": -0.8,
    }
    
    def __init__(self):
        """Initialize the sentiment analyzer."""
        # Combine all keywords
        self.keywords = {**self.BULLISH_WORDS, **self.BEARISH_WORDS}
    
    def analyze_headline(self, headline: str) -> float:
        """
        Analyze sentiment of a single headline.
        
        Args:
            headline: News headline text
            
        Returns:
            Sentiment score from -1 to 1
        """
        headline_lower = headline.lower()
        
        scores = []
        for word, score in self.keywords.items():
            if word in headline_lower:
                scores.append(score)
        
        if not scores:
            return 0.0
        
        # Average the scores and normalize
        raw_score = np.mean(scores)
        normalized = np.clip(raw_score / 2.0, -1.0, 1.0)
        
        return normalized
    
    def analyze_news_batch(self, news_items: List[NewsItem]) -> Tuple[float, Dict]:
        """
        Analyze sentiment from a batch of news items.
        
        Args:
            news_items: List of NewsItem objects
            
        Returns:
            Tuple of (composite_sentiment, details)
        """
        if not news_items:
            return 0.0, {"count": 0, "message": "No news available"}
        
        # Analyze each headline
        for item in news_items:
            item.sentiment = self.analyze_headline(item.title)
        
        # Weight by recency (more recent = higher weight)
        now = datetime.now()
        weighted_sentiments = []
        weights = []
        
        for item in news_items:
            # Age in hours
            if item.timestamp:
                try:
                    age_hours = (now - item.timestamp).total_seconds() / 3600
                except:
                    age_hours = 24
            else:
                age_hours = 24
            
            # Decay weight: recent news matters more
            weight = np.exp(-age_hours / 48)  # Half-life of 48 hours
            weight *= item.relevance
            
            weighted_sentiments.append(item.sentiment * weight)
            weights.append(weight)
        
        # Calculate weighted average
        total_weight = sum(weights)
        if total_weight > 0:
            composite = sum(weighted_sentiments) / total_weight
        else:
            composite = 0.0
        
        # Classify sentiment
        if composite >= 0.5:
            classification = "Very Bullish"
        elif composite >= 0.2:
            classification = "Bullish"
        elif composite >= -0.2:
            classification = "Neutral"
        elif composite >= -0.5:
            classification = "Bearish"
        else:
            classification = "Very Bearish"
        
        details = {
            "count": len(news_items),
            "composite": composite,
            "classification": classification,
            "bullish_count": sum(1 for i in news_items if i.sentiment > 0.1),
            "bearish_count": sum(1 for i in news_items if i.sentiment < -0.1),
            "neutral_count": sum(1 for i in news_items if abs(i.sentiment) <= 0.1),
        }
        
        return composite, details


class NewsFetcher:
    """
    Fetches financial news from various sources.
    
    Currently uses Yahoo Finance. Can be extended to use:
    - NewsAPI (requires API key)
    - Alpha Vantage News
    - Finnhub
    - Benzinga
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the news fetcher.
        
        Args:
            api_key: Optional API key for premium news sources
        """
        self.api_key = api_key or os.environ.get("NEWS_API_KEY")
        self.analyzer = SentimentAnalyzer()
    
    def fetch_yahoo_news(self, symbol: str, max_items: int = 10) -> List[NewsItem]:
        """
        Fetch news from Yahoo Finance.
        
        Args:
            symbol: Stock symbol
            max_items: Maximum number of news items
            
        Returns:
            List of NewsItem objects
        """
        if not YFINANCE_AVAILABLE:
            return []
        
        try:
            ticker = yf.Ticker(symbol)
            news = ticker.news
            
            items = []
            for article in news[:max_items]:
                timestamp = datetime.fromtimestamp(article.get("providerPublishTime", 0))
                
                item = NewsItem(
                    title=article.get("title", ""),
                    source=article.get("publisher", "Yahoo Finance"),
                    timestamp=timestamp,
                    relevance=1.0 if symbol.upper() in article.get("title", "").upper() else 0.7,
                )
                items.append(item)
            
            return items
            
        except Exception as e:
            print(f"Error fetching Yahoo news: {e}")
            return []
    
    def fetch_general_market_news(self, max_items: int = 10) -> List[NewsItem]:
        """
        Fetch general market news using major indices.
        
        Returns:
            List of NewsItem objects
        """
        all_news = []
        
        for symbol in ["SPY", "QQQ", "^VIX"]:
            news = self.fetch_yahoo_news(symbol, max_items=5)
            all_news.extend(news)
        
        # Remove duplicates by title
        seen = set()
        unique_news = []
        for item in all_news:
            if item.title not in seen:
                seen.add(item.title)
                unique_news.append(item)
        
        return unique_news[:max_items]
    
    def get_sentiment(self, symbol: Optional[str] = None) -> Tuple[float, Dict]:
        """
        Get sentiment score for a symbol or general market.
        
        Args:
            symbol: Stock symbol (None for general market)
            
        Returns:
            Tuple of (sentiment_score, details)
        """
        if symbol:
            news = self.fetch_yahoo_news(symbol)
        else:
            news = self.fetch_general_market_news()
        
        return self.analyzer.analyze_news_batch(news)
    
    def get_trading_signal(self, symbol: str) -> Dict:
        """
        Get a trading signal based on news sentiment.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Trading signal dictionary
        """
        sentiment, details = self.get_sentiment(symbol)
        
        # Determine signal
        if sentiment >= 0.4:
            signal = "STRONG_BUY"
            confidence = min(sentiment, 1.0)
        elif sentiment >= 0.15:
            signal = "BUY"
            confidence = sentiment / 0.4
        elif sentiment <= -0.4:
            signal = "STRONG_SELL"
            confidence = min(abs(sentiment), 1.0)
        elif sentiment <= -0.15:
            signal = "SELL"
            confidence = abs(sentiment) / 0.4
        else:
            signal = "HOLD"
            confidence = 1.0 - abs(sentiment) / 0.15
        
        return {
            "symbol": symbol,
            "signal": signal,
            "sentiment": sentiment,
            "confidence": confidence,
            "classification": details["classification"],
            "news_count": details["count"],
            "bullish_count": details.get("bullish_count", 0),
            "bearish_count": details.get("bearish_count", 0),
        }


def get_news_sentiment(symbol: str) -> Tuple[float, str]:
    """
    Convenience function to get news sentiment for a symbol.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        Tuple of (sentiment_score, classification)
    """
    fetcher = NewsFetcher()
    sentiment, details = fetcher.get_sentiment(symbol)
    return sentiment, details.get("classification", "Neutral")


if __name__ == "__main__":
    # Demo
    print("📰 News Sentiment Analysis Demo\n")
    
    fetcher = NewsFetcher()
    
    symbols = ["AAPL", "QQQ", "SPY"]
    
    for symbol in symbols:
        signal = fetcher.get_trading_signal(symbol)
        
        print(f"{'='*50}")
        print(f"📈 {symbol}")
        print(f"{'='*50}")
        print(f"   Sentiment: {signal['sentiment']:.2f}")
        print(f"   Classification: {signal['classification']}")
        print(f"   Signal: {signal['signal']}")
        print(f"   Confidence: {signal['confidence']:.1%}")
        print(f"   News analyzed: {signal['news_count']}")
        print(f"   Bullish headlines: {signal['bullish_count']}")
        print(f"   Bearish headlines: {signal['bearish_count']}")
        print()
