from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def create_session_factory(database_url: str):
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory
