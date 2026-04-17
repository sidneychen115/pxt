import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.core.database import Base

TEST_DB_URL = "postgresql+asyncpg://cx_user:cx_pass@localhost:5432/pxt_test"


@pytest.fixture(scope="session")
def engine():
    return create_async_engine(TEST_DB_URL, echo=False)


@pytest.fixture(autouse=True, scope="session")
async def setup_db(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def session(engine) -> AsyncSession:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
