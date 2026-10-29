from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.deps import get_score_service
from app.domain.schemas import ScoreRequest
from app.services.score_service import ScoreService

router = APIRouter()


@router.post("/score")
async def score(
    body: ScoreRequest,
    service: ScoreService = Depends(get_score_service),
) -> JSONResponse:
    result = await service.score(body)
    return JSONResponse(
        status_code=result.status_code,
        content=result.body,
        headers=result.headers,
    )
