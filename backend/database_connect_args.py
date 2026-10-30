from typing import Any, Callable, Dict, Set
from uuid import uuid4

from sqlalchemy.engine import URL, make_url


class AsyncpgConnectArgsFactory:
    """Builds asyncpg connect_args safe for transaction poolers and local Postgres."""

    _LOCAL_HOSTS: Set[str] = {"localhost", "127.0.0.1", "::1"}

    def __init__(self, database_url: str, connection_timeout_seconds: float = 30.0):
        self._url: URL = make_url(database_url)
        self._connection_timeout_seconds = connection_timeout_seconds

    def build(self) -> Dict[str, Any]:
        connect_args: Dict[str, Any] = {
            "prepared_statement_cache_size": 0,
            "prepared_statement_name_func": self.build_prepared_statement_name_func(),
            "timeout": self._connection_timeout_seconds,
        }
        if self.requires_ssl():
            connect_args["ssl"] = "require"
        return connect_args

    def requires_ssl(self) -> bool:
        host = (self._url.host or "").lower()
        return host not in self._LOCAL_HOSTS

    @staticmethod
    def build_prepared_statement_name_func() -> Callable[[], str]:
        def _unique_prepared_statement_name() -> str:
            return f"__asyncpg_{uuid4().hex}__"

        return _unique_prepared_statement_name
