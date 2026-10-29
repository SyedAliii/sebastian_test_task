from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging.logger import correlation_manager, logger


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path == "/health":
            return await call_next(request)
        client = request.client.host if request.client else "-"
        correlation_id = logger.server_request_in(request.method, request.url.path, client)
        request.state.correlation_id = correlation_id
        try:
            response = await call_next(request)
        except Exception:
            correlation_manager.clear_correlation(correlation_id)
            raise
        logger.server_response_out(response.status_code, request.url.path, correlation_id=correlation_id)
        correlation_manager.clear_correlation(correlation_id)
        response.headers["X-Correlation-ID"] = correlation_id
        return response
