"""Request tracing middleware — attaches a unique ID to every request.

Clients can pass X-Request-ID; otherwise one is generated. The ID is echoed
back in the response header and included in all log lines via contextvars.
"""
import uuid
import logging
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestTracingMiddleware(BaseHTTPMiddleware):
    """Inject X-Request-ID into every request/response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request_id_var.set(req_id)

        logger.debug(
            "request_started method=%s path=%s req_id=%s",
            request.method, request.url.path, req_id,
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id

        logger.debug(
            "request_completed status=%s req_id=%s",
            response.status_code, req_id,
        )
        return response
