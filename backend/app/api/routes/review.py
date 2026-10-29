from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_caller, get_review_service
from app.db.models import User
from app.services.review_service import ReviewService

router = APIRouter()


def _require_admin(caller: User) -> None:
    if caller.role != "admin":
        raise HTTPException(status_code=403, detail="admin only")


@router.get("/review")
async def review_list(
    caller: User = Depends(get_caller),
    service: ReviewService = Depends(get_review_service),
) -> list:
    _require_admin(caller)
    return await service.list_held(caller.workspace_id)


@router.post("/review/{media_id}/approve")
async def approve(
    media_id: str,
    caller: User = Depends(get_caller),
    service: ReviewService = Depends(get_review_service),
) -> dict:
    return await _resolve(media_id, caller, service, "published")


@router.post("/review/{media_id}/reject")
async def reject(
    media_id: str,
    caller: User = Depends(get_caller),
    service: ReviewService = Depends(get_review_service),
) -> dict:
    return await _resolve(media_id, caller, service, "blocked")


async def _resolve(media_id: str, caller: User, service: ReviewService, status: str) -> dict:
    _require_admin(caller)
    outcome = await service.resolve(caller.workspace_id, media_id, caller.id, status)
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="not found")
    if outcome == "conflict":
        raise HTTPException(status_code=409, detail="not a review hold")
    return {"id": media_id, "status": status}
