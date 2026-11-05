from typing import Any, AsyncGenerator, Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from .config import PROJECT_ROOT, get_settings


class Base(DeclarativeBase):
    pass


_sync_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker[Session]] = None
_active_db_backend: str = "uninitialized"


def _build_sync_engine() -> Engine:
    global _active_db_backend
    settings = get_settings()
    url = settings.database_sync_url

    if url.startswith("sqlite"):
        _active_db_backend = "sqlite"
        connect_args = {"check_same_thread": False}
        pool_cls = StaticPool if ":memory:" in url else NullPool
        return create_engine(url, connect_args=connect_args, poolclass=pool_cls)

    eng: Optional[Engine] = None
    try:
        eng = (
            create_engine(url, echo=settings.db_echo, poolclass=NullPool)
            if settings.db_pool_mode == "null"
            else create_engine(
                url,
                echo=settings.db_echo,
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                pool_pre_ping=True,
            )
        )
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        _active_db_backend = "postgresql"
        return eng
    except Exception:
        if eng is not None:
            eng.dispose()
        if not settings.demo_mode:
            raise
        fallback_path = (PROJECT_ROOT / "data" / "noir_platform.db").resolve()
        fallback_path.parent.mkdir(parents=True, exist_ok=True)
        _active_db_backend = "sqlite_demo_fallback"
        return create_engine(
            f"sqlite:///{fallback_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )


def get_sync_engine() -> Engine:
    global _sync_engine, _SessionLocal
    if _sync_engine is None:
        _sync_engine = _build_sync_engine()
        _SessionLocal = sessionmaker(bind=_sync_engine, autocommit=False, autoflush=False, expire_on_commit=False)
    return _sync_engine


def set_sync_engine(engine: Optional[Engine] = None, backend_label: str = "custom") -> None:
    global _sync_engine, _SessionLocal, _active_db_backend
    _sync_engine = engine
    _SessionLocal = (
        sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
        if engine is not None
        else None
    )
    _active_db_backend = backend_label if engine is not None else "uninitialized"


def get_active_db_backend() -> str:
    if _sync_engine is None:
        get_sync_engine()
    return _active_db_backend


def get_db() -> Generator[Session, None, None]:
    if _SessionLocal is None:
        get_sync_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


def build_async_engine() -> Any:
    settings = get_settings()
    if settings.db_pool_mode == "null":
        return create_async_engine(settings.database_url, echo=settings.db_echo, poolclass=NullPool)
    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
    )


async_engine = build_async_engine()
AsyncSessionLocal = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
