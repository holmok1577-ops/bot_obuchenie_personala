from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy import text

from database.models import Base


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, future=True, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            text(
                """
                ALTER TABLE training_results
                ADD COLUMN IF NOT EXISTS section_index INTEGER NOT NULL DEFAULT 1,
                ADD COLUMN IF NOT EXISTS total_sections INTEGER NOT NULL DEFAULT 1,
                ADD COLUMN IF NOT EXISTS section_title VARCHAR(255) NOT NULL DEFAULT 'Общий результат',
                ADD COLUMN IF NOT EXISTS section_attempt INTEGER NOT NULL DEFAULT 1,
                ADD COLUMN IF NOT EXISTS passed_to_next_section BOOLEAN NOT NULL DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS course_completed BOOLEAN NOT NULL DEFAULT FALSE
                """
            )
        )
