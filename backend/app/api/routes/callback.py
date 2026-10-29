from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.deps import get_callback_service, get_settings
from app.config import Settings
from app.core.logging.logger import logger
from app.domain.signature import signatures_match
from app.services.callback_service import CallbackService

router = APIRouter()


@router.post("/provider/callback")
async def provider_callback(
    request: Request,
    settings: Settings = Depends(get_settings),
    service: CallbackService = Depends(get_callback_service),
) -> JSONResponse:
    raw = await request.body()
    signature = request.headers.get("X-Signature")
    if not signatures_match(raw, signature, settings.provider_hmac_secret):
        logger.webhook_fail("provider", source="provider", error="bad signature")
        return JSONResponse(status_code=401, content={"detail": "bad signature"})
    result = await service.apply(raw)
    return JSONResponse(status_code=result.status_code, content=result.body)
