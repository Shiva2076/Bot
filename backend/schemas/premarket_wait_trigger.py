from enum import Enum


class PremarketWaitTrigger(str, Enum):
    LARGE_GAP = "LARGE_GAP"
    HIGH_VIX = "HIGH_VIX"
    CONFLICT = "CONFLICT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    DEFAULT = "DEFAULT"
    NONE = "NONE"
