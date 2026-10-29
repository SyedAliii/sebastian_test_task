from fastapi import APIRouter, Depends

from app.api.deps import get_store
from app.domain.schemas import ControlRequest
from app.repo.store import MemoryProviderStore

router = APIRouter()


@router.post("/_control")
async def set_control(
    body: ControlRequest,
    store: MemoryProviderStore = Depends(get_store),
) -> dict:
    return await store.set_control(body.mode, body.delay_ms, body.error_kind)
