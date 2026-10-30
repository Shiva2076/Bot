import os
from typing import Mapping, Optional


class RuntimeEnvironment:
    """Detects hosting constraints that affect startup and background workers."""

    def __init__(self, environ: Optional[Mapping[str, str]] = None):
        self._environ = environ if environ is not None else os.environ

    @property
    def is_vercel(self) -> bool:
        return bool(self._environ.get("VERCEL"))

    @property
    def should_start_background_workers(self) -> bool:
        return not self.is_vercel
