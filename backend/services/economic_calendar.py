"""
Economic Calendar — tracks high-impact events for Indian and global markets.
"""
from datetime import datetime, timedelta
from typing import List, Dict
import pytz

IST = pytz.timezone("Asia/Kolkata")


def get_upcoming_events() -> List[Dict]:
    """
    Return hardcoded + dynamically computed upcoming high-impact events.
    In production, this would scrape investing.com or use a paid calendar API.
    """
    now = datetime.now(IST)
    events = []

    # --- Static recurring events (approximate dates) ---
    static_events = [
        # RBI MPC meetings (bi-monthly)
        {"name": "RBI MPC Decision", "impact": "HIGH", "category": "Monetary Policy",
         "description": "Reserve Bank of India Monetary Policy Committee rate decision"},
        {"name": "India CPI Inflation", "impact": "HIGH", "category": "Inflation",
         "description": "Consumer Price Index data release"},
        {"name": "India IIP Data", "impact": "MEDIUM", "category": "Industrial Output",
         "description": "Index of Industrial Production data"},
        {"name": "US FOMC Meeting", "impact": "HIGH", "category": "Global",
         "description": "US Federal Reserve interest rate decision — impacts FII flows to India"},
        {"name": "US CPI Inflation", "impact": "HIGH", "category": "Global",
         "description": "US inflation data — major market mover"},
        {"name": "US Non-Farm Payroll", "impact": "HIGH", "category": "Global",
         "description": "US jobs data — impacts global risk appetite"},
        {"name": "India GDP Data", "impact": "HIGH", "category": "Economic Growth",
         "description": "Quarterly GDP growth rate"},
        {"name": "Nifty F&O Expiry", "impact": "MEDIUM", "category": "Market",
         "description": "Monthly futures and options expiry — expect high volatility"},
        {"name": "Q1 Earnings Season", "impact": "MEDIUM", "category": "Earnings",
         "description": "Corporate quarterly earnings season begins"},
    ]

    # Simulate upcoming events by assigning future dates
    for i, event in enumerate(static_events):
        days_away = (i * 7) % 45 + 1  # Spread across next 45 days
        event_date = now + timedelta(days=days_away)
        hours_away = days_away * 24
        events.append({
            **event,
            "date": event_date.strftime("%Y-%m-%d"),
            "days_away": days_away,
            "hours_away": hours_away,
            "warning": hours_away <= 48,
        })

    # Sort by date
    events.sort(key=lambda x: x["days_away"])
    return events


def get_events_within_48h() -> List[Dict]:
    """Return only events happening within 48 hours."""
    return [e for e in get_upcoming_events() if e.get("hours_away", 999) <= 48]
