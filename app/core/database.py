from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import settings

DATABASE_URL = settings.pg_dsn

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    connect_args={"server_settings": {"client_encoding": "utf8"}},
)

async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

Base = declarative_base()

async def get_async_db() -> AsyncSession:
    async with async_session() as session:
        yield session
