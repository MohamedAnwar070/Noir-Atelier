from typing import Any, AsyncGenerator

from .config import get_settings

try:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.orm import DeclarativeBase
    from sqlalchemy.pool import NullPool

    class Base(DeclarativeBase):
        pass

    def build_async_engine() -> Any:
        settings = get_settings()
        if settings.db_pool_mode == "null":
            return create_async_engine(
                settings.database_url,
                echo=settings.db_echo,
                poolclass=NullPool,
            )
        return create_async_engine(
            settings.database_url,
            echo=settings.db_echo,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
        )

    async_engine = build_async_engine()
    AsyncSessionLocal = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSessionLocal() as session:
            yield session

except ImportError:
    Base = object  # type: ignore[misc,assignment]
    async_engine = None
    AsyncSessionLocal = None

