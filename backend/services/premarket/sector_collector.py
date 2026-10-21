from typing import List, Tuple

from engines.sector_rotation import get_sector_performance
from schemas.premarket import SectorSnapshot


class SectorCollector:
    async def collect(self) -> Tuple[List[SectorSnapshot], List[SectorSnapshot]]:
        sectors = await get_sector_performance()
        strongest = [
            SectorSnapshot(name=s["name"], change_pct=float(s["change_pct"]), status=s["status"])
            for s in sectors[:3]
        ]
        weakest = [
            SectorSnapshot(name=s["name"], change_pct=float(s["change_pct"]), status=s["status"])
            for s in sectors[-3:]
        ]
        return strongest, weakest
