#!/usr/bin/env python3
"""
Economic News Filter for Forex Bot
Fetches high-impact economic calendar events and implements a risk blackout gate
around high-impact events (e.g. CPI, NFP, FOMC, Central Bank rate decisions).
"""

import os
import json
import time
import requests
from datetime import datetime, timezone, timedelta
import dateutil.parser

CALENDAR_CACHE_FILE = "/tmp/forex_economic_calendar.json"
CACHE_TTL_SECONDS = 14400  # 4 hours


class EconomicNewsFilter:
    def __init__(self, cache_file: str = CALENDAR_CACHE_FILE, cache_ttl: int = CACHE_TTL_SECONDS):
        self.cache_file = cache_file
        self.cache_ttl = cache_ttl
        self.events = []
        self._load_calendar()

    def _load_calendar(self):
        """Load calendar from local cache or fetch fresh feed."""
        if os.path.exists(self.cache_file):
            try:
                mtime = os.path.getmtime(self.cache_file)
                if time.time() - mtime < self.cache_ttl:
                    with open(self.cache_file, "r") as f:
                        self.events = json.load(f)
                    if self.events:
                        return
            except Exception as e:
                print(f"⚠️ [NewsFilter] Error reading calendar cache: {e}")

        self.fetch_fresh_calendar()

    def fetch_fresh_calendar(self):
        """Fetch weekly calendar from open feeds with robust fallback."""
        feeds = [
            "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            "https://nfs.faireconomy.media/ff_calendar_nextweek.json"
        ]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.forexfactory.com/"
        }
        
        fetched_events = []
        for url in feeds:
            try:
                r = requests.get(url, headers=headers, timeout=6)
                if r.status_code == 200:
                    raw_events = r.json()
                    for ev in raw_events:
                        impact = ev.get("impact", "")
                        if impact in ["High", "Medium"]:
                            fetched_events.append({
                                "title": ev.get("title"),
                                "country": ev.get("country", "").upper(),
                                "date": ev.get("date"),
                                "impact": impact,
                                "forecast": ev.get("forecast", ""),
                                "previous": ev.get("previous", "")
                            })
                    if fetched_events:
                        break
            except Exception:
                pass

        if fetched_events:
            self.events = fetched_events
            try:
                with open(self.cache_file, "w") as f:
                    json.dump(self.events, f, indent=2)
                print(f"✅ [NewsFilter] Fetched & cached {len(self.events)} high/medium impact macro events.")
            except Exception as e:
                print(f"⚠️ [NewsFilter] Failed to save calendar cache: {e}")
        else:
            # Generate baseline recurring macro recurring schedule if web feeds are rate-limited
            print("ℹ️ [NewsFilter] Remote feed throttled, generating baseline central bank / macro schedule...")
            self._load_baseline_macro_schedule()

    def _load_baseline_macro_schedule(self):
        """Build standard macro high-impact risk checkpoints (NFP, CPI, FOMC, Rate decisions)."""
        now = datetime.now(timezone.utc)
        baseline = []
        # Scheduled upcoming weekly major releases (US, CAD, EUR, GBP, JPY)
        upcoming_events = [
            ("CAD", "CPI m/m", "2026-08-17T12:30:00Z"),
            ("CAD", "Median CPI y/y", "2026-08-17T12:30:00Z"),
            ("GBP", "Claimant Count Change", "2026-08-18T06:00:00Z"),
            ("GBP", "CPI y/y", "2026-08-19T06:00:00Z"),
            ("USD", "FOMC Meeting Minutes", "2026-08-19T18:00:00Z"),
            ("USD", "Unemployment Claims", "2026-08-20T12:30:00Z"),
            ("USD", "Jackson Hole Symposium", "2026-08-21T14:00:00Z"),
            ("JPY", "Tokyo Core CPI y/y", "2026-08-21T23:30:00Z"),
            ("EUR", "ECB Monetary Policy Meeting Accounts", "2026-08-27T11:30:00Z"),
            ("USD", "Core PCE Price Index m/m", "2026-08-28T12:30:00Z"),
            ("USD", "Non-Farm Employment Change (NFP)", "2026-09-04T12:30:00Z"),
        ]
        for c, t, d in upcoming_events:
            baseline.append({
                "country": c,
                "title": t,
                "date": d,
                "impact": "High",
                "forecast": "",
                "previous": ""
            })
        self.events = baseline

    def is_blackout_active(self, instrument: str, pre_minutes: int = 30, post_minutes: int = 15) -> tuple:
        """
        Check if the instrument is currently within a news blackout window.
        
        Args:
            instrument: e.g. "USD_JPY", "EUR_USD", "USD_CAD", "GBP_USD", "AUD_USD"
            pre_minutes: Minutes before the event to block entries (default: 30)
            post_minutes: Minutes after the event to block entries (default: 15)
            
        Returns:
            (is_blocked: bool, reason: str, next_event: dict or None)
        """
        if not self.events:
            return False, "No active news blackout", None

        parts = instrument.upper().split("_")
        if len(parts) != 2:
            return False, "Invalid instrument format", None
        curr1, curr2 = parts[0], parts[1]

        now_utc = datetime.now(timezone.utc)

        for ev in self.events:
            ev_country = ev.get("country", "")
            if ev.get("impact") != "High":
                continue

            if ev_country in [curr1, curr2]:
                try:
                    ev_time = dateutil.parser.isoparse(ev["date"])
                    if ev_time.tzinfo is None:
                        ev_time = ev_time.replace(tzinfo=timezone.utc)
                    else:
                        ev_time = ev_time.astimezone(timezone.utc)

                    diff_seconds = (ev_time - now_utc).total_seconds()
                    diff_minutes = diff_seconds / 60.0

                    if -post_minutes <= diff_minutes <= pre_minutes:
                        time_desc = f"in {int(diff_minutes)}m" if diff_minutes > 0 else f"{int(abs(diff_minutes))}m ago"
                        reason = f"[{ev_country}] {ev['title']} ({time_desc})"
                        return True, reason, ev

                except Exception:
                    continue

        return False, "News Clear", None


if __name__ == "__main__":
    filter_engine = EconomicNewsFilter()
    print(f"Total events in memory: {len(filter_engine.events)}")
    for inst in ["USD_JPY", "USD_CAD", "EUR_USD", "GBP_USD", "AUD_USD"]:
        blocked, reason, ev = filter_engine.is_blackout_active(inst)
        print(f"{inst}: Blocked={blocked} | Reason={reason}")

