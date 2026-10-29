from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def insert_seed(session: AsyncSession) -> None:
    await session.execute(
        text(
            """
            insert into workspaces (id, verified)
            values ('ws_verified', true), ('ws_unverified', false)
            on conflict (id) do nothing
            """
        )
    )
    await session.execute(
        text(
            """
            insert into users (id, workspace_id, role)
            values
                ('admin_v', 'ws_verified', 'admin'),
                ('member_v', 'ws_verified', 'member'),
                ('admin_u', 'ws_unverified', 'admin'),
                ('member_u', 'ws_unverified', 'member')
            on conflict (id) do nothing
            """
        )
    )
