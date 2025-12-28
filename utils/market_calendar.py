"""
Forex Market Calendar - Check if markets are open

Forex markets are open 24/5:
- Opens: Sunday 5:00 PM ET (Sydney open)
- Closes: Friday 5:00 PM ET (New York close)

Major holidays when forex is closed:
- Christmas Day (Dec 25)
- New Year's Day (Jan 1)
- Some brokers close early on Christmas Eve and New Year's Eve

Author: Forex Bot Team
Date: 2025-12-25
"""

from datetime import datetime, timedelta
import pytz


# Major forex holidays (month, day) - markets fully closed
FOREX_HOLIDAYS = [
    (1, 1),  # New Year's Day
    (12, 25),  # Christmas Day
]

# Early close days (month, day) - markets close at 5pm ET instead of normal hours
EARLY_CLOSE_DAYS = [
    (12, 24),  # Christmas Eve
    (12, 31),  # New Year's Eve
]


def is_forex_market_open(check_time: datetime = None) -> tuple[bool, str]:
    """
    Check if forex markets are currently open.

    Returns:
        tuple: (is_open: bool, reason: str)
    """
    # Use current time if not specified
    if check_time is None:
        check_time = datetime.now(pytz.UTC)

    # Convert to Eastern Time (forex uses ET for market hours)
    eastern = pytz.timezone("US/Eastern")
    et_time = check_time.astimezone(eastern)

    # Check for major holidays
    month_day = (et_time.month, et_time.day)
    if month_day in FOREX_HOLIDAYS:
        return False, f"Market closed for holiday ({et_time.strftime('%B %d')})"

    # Get day of week (0=Monday, 6=Sunday)
    weekday = et_time.weekday()
    current_hour = et_time.hour

    # Saturday - fully closed
    if weekday == 5:  # Saturday
        return False, "Market closed (Saturday)"

    # Sunday - opens at 5:00 PM ET
    if weekday == 6:  # Sunday
        if current_hour < 17:  # Before 5 PM
            return False, "Market closed (Sunday, opens at 5:00 PM ET)"
        else:
            return True, "Market open (Sunday evening session)"

    # Friday - closes at 5:00 PM ET
    if weekday == 4:  # Friday
        if current_hour >= 17:  # After 5 PM
            return False, "Market closed (Friday after 5:00 PM ET)"

    # Check early close days
    if month_day in EARLY_CLOSE_DAYS:
        if current_hour >= 17:  # After 5 PM
            return (
                False,
                f"Market closed early for holiday ({et_time.strftime('%B %d')})",
            )

    # Monday-Friday before 5 PM Friday = market is open
    return True, f"Market open ({et_time.strftime('%A %I:%M %p ET')})"


def get_next_market_open(from_time: datetime = None) -> datetime:
    """
    Get the next time the forex market will be open.

    Returns:
        datetime: Next market open time in UTC
    """
    if from_time is None:
        from_time = datetime.now(pytz.UTC)

    eastern = pytz.timezone("US/Eastern")
    et_time = from_time.astimezone(eastern)

    weekday = et_time.weekday()

    # If Saturday, next open is Sunday 5 PM
    if weekday == 5:
        days_until_sunday = 1
        next_open = et_time.replace(hour=17, minute=0, second=0, microsecond=0)
        next_open = next_open + timedelta(days=days_until_sunday)

    # If Friday after 5 PM, next open is Sunday 5 PM
    elif weekday == 4 and et_time.hour >= 17:
        days_until_sunday = 2
        next_open = et_time.replace(hour=17, minute=0, second=0, microsecond=0)
        next_open = next_open + timedelta(days=days_until_sunday)

    # If Sunday before 5 PM, opens today at 5 PM
    elif weekday == 6 and et_time.hour < 17:
        next_open = et_time.replace(hour=17, minute=0, second=0, microsecond=0)

    # Market is open now
    else:
        return from_time

    return next_open.astimezone(pytz.UTC)


def hours_until_market_open(from_time: datetime = None) -> float:
    """
    Get hours until market opens.

    Returns:
        float: Hours until market opens (0 if already open)
    """
    is_open, _ = is_forex_market_open(from_time)
    if is_open:
        return 0.0

    if from_time is None:
        from_time = datetime.now(pytz.UTC)

    next_open = get_next_market_open(from_time)
    delta = next_open - from_time
    return delta.total_seconds() / 3600


# Quick test when run directly
if __name__ == "__main__":
    from datetime import timedelta

    print("=" * 50)
    print("FOREX MARKET CALENDAR TEST")
    print("=" * 50)

    is_open, reason = is_forex_market_open()
    print(f"\nCurrent status: {'OPEN' if is_open else 'CLOSED'}")
    print(f"Reason: {reason}")

    if not is_open:
        hours = hours_until_market_open()
        print(f"Hours until open: {hours:.1f}")

    print("\n--- Testing specific times ---")

    # Test cases
    eastern = pytz.timezone("US/Eastern")
    test_cases = [
        ("Christmas Day", eastern.localize(datetime(2025, 12, 25, 12, 0))),
        ("Saturday", eastern.localize(datetime(2025, 12, 27, 12, 0))),
        ("Sunday Morning", eastern.localize(datetime(2025, 12, 28, 10, 0))),
        ("Sunday Evening", eastern.localize(datetime(2025, 12, 28, 18, 0))),
        ("Monday", eastern.localize(datetime(2025, 12, 29, 12, 0))),
        ("Friday Afternoon", eastern.localize(datetime(2025, 12, 26, 14, 0))),
        ("Friday After Close", eastern.localize(datetime(2025, 12, 26, 18, 0))),
    ]

    for name, test_time in test_cases:
        is_open, reason = is_forex_market_open(test_time)
        status = "OPEN" if is_open else "CLOSED"
        print(f"{name}: {status} - {reason}")
