from fastapi import APIRouter, Depends

from app.api.deps import get_store
from app.repo.store import MemoryProviderStore

router = APIRouter()


@router.get("/_stats")
async def stats(store: MemoryProviderStore = Depends(get_store)) -> dict:
    return {"calls": await store.get_calls()}
