from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_caller, get_media_service
from app.db.models import User
from app.domain.schemas import MediaCreated, MediaIn, MediaOut
from app.services.media_service import MediaService

router = APIRouter()


@router.post("/media", status_code=202, response_model=MediaCreated)
async def post_media(
    body: MediaIn,
    request: Request,
    caller: User = Depends(get_caller),
    service: MediaService = Depends(get_media_service),
) -> MediaCreated:
    correlation_id = getattr(request.state, "correlation_id", None)
    return await service.create_media(caller, body, correlation_id=correlation_id)


@router.get("/media/{media_id}", response_model=MediaOut)
async def read_media(
    media_id: str,
    caller: User = Depends(get_caller),
    service: MediaService = Depends(get_media_service),
) -> MediaOut:
    found = await service.get_media(caller, media_id)
    if found is None:
        raise HTTPException(status_code=404, detail="not found")
    return found
