"""
Role-based access control (Phase 12).

`AuthMiddleware` resolves the caller's API key and attaches `api_key_role`
to `request.state` ('admin' or 'member'; static env-var keys are 'admin').
`require_role(...)` turns that into a FastAPI dependency that gates a route.

Self-hosted convenience: when `REQUIRE_AUTH=false` there is no authenticated
key, so a role cannot be resolved. In that single-operator mode every role
check passes — RBAC only bites once auth is switched on.
"""

from fastapi import Depends, HTTPException, Request

from app.config import settings


def require_role(*allowed: str):
    """
    Build a dependency that allows the request only if the caller's role is
    in `allowed`. Usage:  dependencies=[Depends(require_role("admin"))]
    """

    async def _checker(request: Request) -> str:
        role = getattr(request.state, "api_key_role", None)

        if role is None:
            # No authenticated key on this request.
            if not settings.require_auth:
                return "admin"  # self-hosted single-operator mode
            raise HTTPException(
                status_code=403,
                detail="This endpoint requires an authenticated API key.",
            )

        if role not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient role. Requires: {' or '.join(allowed)}.",
            )
        return role

    return _checker


# Common pre-built dependency: admin-only.
require_admin = Depends(require_role("admin"))
