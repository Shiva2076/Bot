"""
Sector Rotation Engine — ranks NSE sectors by relative strength vs NIFTY 50.
"""
import asyncio
from typing import Dict, List
from services.market_data import market_data_service

SECTOR_INDICES = [
    {"symbol": "^CNXIT", "name": "IT", "key": "IT"},
    {"symbol": "^NSEBANK", "name": "Banking", "key": "BANK"},
    {"symbol": "^CNXAUTO", "name": "Auto", "key": "AUTO"},
    {"symbol": "^CNXPHARMA", "name": "Pharma", "key": "PHARMA"},
    {"symbol": "^CNXFMCG", "name": "FMCG", "key": "FMCG"},
    {"symbol": "^CNXMETAL", "name": "Metal", "key": "METAL"},
    {"symbol": "^CNXREALTY", "name": "Realty", "key": "REALTY"},
    {"symbol": "^CNXENERGY", "name": "Energy", "key": "ENERGY"},
    {"symbol": "^CNXINFRA", "name": "Infra", "key": "INFRA"},
]


async def get_sector_performance() -> List[Dict]:
    """Fetch daily % change for all sectors and rank them."""
    tasks = [market_data_service.fetch_live_quote(s["symbol"]) for s in SECTOR_INDICES]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    sectors = []
    for i, result in enumerate(results):
        if isinstance(result, dict):
            change_pct = result.get("change_pct", 0)
            sectors.append({
                "key": SECTOR_INDICES[i]["key"],
                "name": SECTOR_INDICES[i]["name"],
                "symbol": SECTOR_INDICES[i]["symbol"],
                "price": result.get("price"),
                "change_pct": change_pct,
                "status": "LEADING" if change_pct > 0.5 else (
                    "LAGGING" if change_pct < -0.5 else "NEUTRAL"
                ),
            })

    # Sort by change_pct descending
    sectors.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
    for i, s in enumerate(sectors):
        s["rank"] = i + 1

    return sectors


async def get_sector_recommendation() -> Dict:
    """Return leading and lagging sectors with actionable advice."""
    sectors = await get_sector_performance()
    leading = [s for s in sectors if s.get("status") == "LEADING"][:3]
    lagging = [s for s in sectors if s.get("status") == "LAGGING"][-3:]
    lagging_keys = {s["key"] for s in lagging}
    return {
        "sectors": sectors,
        "leading": leading,
        "lagging": lagging,
        "avoid_sectors": list(lagging_keys),
        "advice": (
            f"Focus on {', '.join(s['name'] for s in leading[:2])} today. "
            f"Avoid {', '.join(s['name'] for s in lagging[:2])}."
            if leading and lagging else "Sector data unavailable."
        ),
    }
