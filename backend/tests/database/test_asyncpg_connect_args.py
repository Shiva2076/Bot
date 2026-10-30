from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine

from database_connect_args import AsyncpgConnectArgsFactory


def test_local_url_disables_ssl_and_disables_prepared_statement_cache():
    factory = AsyncpgConnectArgsFactory(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
    )
    connect_args = factory.build()

    assert connect_args["prepared_statement_cache_size"] == 0
    assert "ssl" not in connect_args
    assert connect_args["timeout"] == 30.0
    assert callable(connect_args["prepared_statement_name_func"])


def test_supabase_pooler_url_requires_ssl():
    factory = AsyncpgConnectArgsFactory(
        "postgresql+asyncpg://user:pass@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres"
    )
    connect_args = factory.build()

    assert connect_args["prepared_statement_cache_size"] == 0
    assert connect_args["ssl"] == "require"
    assert connect_args["timeout"] == 30.0


def test_prepared_statement_names_are_unique_and_collision_resistant():
    name_func = AsyncpgConnectArgsFactory.build_prepared_statement_name_func()
    names = {name_func() for _ in range(50)}

    assert len(names) == 50
    assert all(name.startswith("__asyncpg_") and name.endswith("__") for name in names)
    assert all(len(name) > len("__asyncpg____") for name in names)


def test_engine_uses_null_pool_and_factory_connect_args():
    url = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/postgres"
    connect_args = AsyncpgConnectArgsFactory(url).build()
    engine = create_async_engine(url, poolclass=NullPool, connect_args=connect_args)

    assert engine.pool.__class__ is NullPool
    assert engine.url.query.get("prepared_statement_cache_size") in (None, "0")
    # connect_args are applied at connect time; verify factory values remain as configured
    assert connect_args["prepared_statement_cache_size"] == 0
    assert "ssl" not in connect_args
