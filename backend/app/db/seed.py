from sqlalchemy.ext.asyncio import AsyncSession

from app.repo.seed_repo import insert_seed


async def seed(session: AsyncSession) -> None:
    await insert_seed(session)
