"""
Institutional Data Service — fetches FII/DII activity from NSE public APIs.
"""
import aiohttp
from typing import Dict
import json

NSE_FII_DII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


async def get_institutional_data(symbol: str = None) -> Dict:
    """
    Fetch FII and DII daily flows from NSE.
    Returns net buying/selling in Crores.
    """
    try:
        async with aiohttp.ClientSession(headers=NSE_HEADERS) as session:
            # First hit NSE homepage to get cookies
            async with session.get("https://www.nseindia.com/", timeout=aiohttp.ClientTimeout(total=5)):
                pass
            async with session.get(NSE_FII_DII_URL, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    return _parse_fii_dii(data)
    except Exception as e:
        print(f"FII/DII fetch error: {e}")

    # Return mock data when NSE API is unavailable
    return _mock_institutional_data()


def _parse_fii_dii(data) -> Dict:
    """Parse NSE FII/DII API response."""
    try:
        if isinstance(data, list) and len(data) > 0:
            latest = data[0]
            fii_net = float(latest.get("netVal", 0)) if "FII" in str(latest.get("category", "")) else 0
            dii_net = float(latest.get("netVal", 0)) if "DII" in str(latest.get("category", "")) else 0

            fii_entries = [d for d in data if "FII" in str(d.get("category", ""))]
            dii_entries = [d for d in data if "DII" in str(d.get("category", ""))]

            fii_net = sum(float(d.get("netVal", 0)) for d in fii_entries[:1])
            dii_net = sum(float(d.get("netVal", 0)) for d in dii_entries[:1])

            return {
                "fii_net": round(fii_net, 2),
                "dii_net": round(dii_net, 2),
                "delivery_pct": 45.0,  # Would need separate endpoint
                "oi_change_pct": 0,
                "pcr": 1.0,
                "source": "NSE Live",
            }
    except Exception as e:
        print(f"FII/DII parse error: {e}")
    return _mock_institutional_data()


def _mock_institutional_data() -> Dict:
    """Mock data for development/when NSE API is unavailable."""
    import random
    return {
        "fii_net": round(random.uniform(-3000, 3000), 2),
        "dii_net": round(random.uniform(-1500, 2000), 2),
        "delivery_pct": round(random.uniform(35, 70), 1),
        "oi_change_pct": round(random.uniform(-10, 15), 2),
        "pcr": round(random.uniform(0.7, 1.4), 2),
        "source": "Mock (NSE API unavailable)",
    }
