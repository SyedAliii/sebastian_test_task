from fastapi import APIRouter, Depends

from app.api.deps import get_settings
from app.config import Settings

router = APIRouter()


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    _ = settings
    return {"status": "ok"}
