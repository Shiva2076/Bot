"""
Institutional Data Service — fetches FII/DII activity from NSE public APIs.
"""
import aiohttp
from typing import Dict

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
    Returns net buying/selling in Crores, or an explicit unavailable result.
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
                return _unavailable(f"NSE FII/DII HTTP {resp.status}")
    except Exception as e:
        print(f"FII/DII fetch error: {e}")
        return _unavailable(f"NSE FII/DII fetch failed: {type(e).__name__}")


def _parse_fii_dii(data) -> Dict:
    """Parse NSE FII/DII API response."""
    if not isinstance(data, list) or not data:
        return _unavailable("NSE FII/DII response empty")
    try:
        fii_entries = [d for d in data if "FII" in str(d.get("category", ""))]
        dii_entries = [d for d in data if "DII" in str(d.get("category", ""))]
        if not fii_entries or not dii_entries:
            return _unavailable("NSE FII/DII response missing FII or DII rows")
        return {
            "available": True,
            "fii_net": round(float(fii_entries[0].get("netVal", 0)), 2),
            "dii_net": round(float(dii_entries[0].get("netVal", 0)), 2),
            "source": "NSE Live",
        }
    except (TypeError, ValueError) as e:
        print(f"FII/DII parse error: {e}")
        return _unavailable("NSE FII/DII response could not be parsed")


def _unavailable(reason: str) -> Dict:
    return {"available": False, "source": "unavailable", "reason": reason}
