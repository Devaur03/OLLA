"""
API key management endpoints.

POST  /api/v1/keys/register  — register an email address → get first free-tier key
GET   /api/v1/keys           — list keys for the authenticated user
POST  /api/v1/keys           — create an additional key
DELETE /api/v1/keys/{key_id} — revoke a key

Security notes:
  - The raw key is returned ONCE on creation and never stored — only the SHA-256
    hash is kept in the DB.
  - All management endpoints (except /register) require a valid X-API-Key.
  - /register is public so new users can bootstrap themselves.
"""

import hashlib
import logging
import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.db.api_key import ApiKey
from app.models.db.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/keys", tags=["keys"])

KEY_PREFIX = "hsa_"   # hybrid-search-agent
MAX_KEYS_PER_USER = 5


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    name:  str = Field(default="Default key", max_length=100)


class RegisterResponse(BaseModel):
    message:    str
    api_key:    str   # shown once — user must copy it
    key_prefix: str
    user_id:    str
    plan:       str


class KeyInfo(BaseModel):
    id:          str
    key_prefix:  str
    name:        str
    is_active:   bool
    created_at:  datetime
    last_used_at: datetime | None


class CreateKeyRequest(BaseModel):
    name: str = Field(default="New key", max_length=100)


class CreateKeyResponse(BaseModel):
    message:    str
    api_key:    str   # shown once
    key_prefix: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_key() -> tuple[str, str, str]:
    """Returns (raw_key, key_hash, key_prefix)."""
    raw   = KEY_PREFIX + secrets.token_urlsafe(32)
    h     = hashlib.sha256(raw.encode()).hexdigest()
    prefix = raw[:12]   # e.g. "hsa_AbCdEfGh"
    return raw, h, prefix


def _get_user_id_from_request(request: Request) -> str:
    """Extract user_id set by AuthMiddleware, or raise 401."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user_id


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    body: RegisterRequest,
    db:   AsyncSession = Depends(get_db_session),
):
    """
    Public endpoint — register a new email and receive a free-tier API key.
    If the email already exists the existing user is returned with a new key
    (up to MAX_KEYS_PER_USER).
    """
    email = body.email.lower().strip()

    # Find or create user
    result = await db.execute(select(User).where(User.email == email))
    user   = result.scalar_one_or_none()

    if not user:
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            plan="free",
            is_active=True,
        )
        db.add(user)
        await db.flush()
        logger.info("keys.register: created user %s (%s)", user.id, email)
    else:
        # Check key count
        count_result = await db.execute(
            select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.is_active == True)  # noqa
        )
        existing = count_result.scalars().all()
        if len(existing) >= MAX_KEYS_PER_USER:
            raise HTTPException(
                status_code=409,
                detail=f"You already have {MAX_KEYS_PER_USER} active keys. Revoke one first.",
            )

    raw_key, key_hash, key_prefix = _generate_key()
    api_key = ApiKey(
        id=str(uuid.uuid4()),
        user_id=user.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=body.name,
        is_active=True,
    )
    db.add(api_key)
    await db.commit()

    logger.info("keys.register: issued key %s for user %s", key_prefix, user.id)

    return RegisterResponse(
        message="API key created. Copy it now — it will not be shown again.",
        api_key=raw_key,
        key_prefix=key_prefix,
        user_id=user.id,
        plan=user.plan,
    )


@router.get("", response_model=list[KeyInfo])
async def list_keys(
    request: Request,
    db:      AsyncSession = Depends(get_db_session),
):
    """List all active API keys for the authenticated user."""
    user_id = _get_user_id_from_request(request)
    result  = await db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == user_id)
        .order_by(ApiKey.created_at.desc())
    )
    keys = result.scalars().all()
    return [
        KeyInfo(
            id=k.id,
            key_prefix=k.key_prefix,
            name=k.name,
            is_active=k.is_active,
            created_at=k.created_at,
            last_used_at=k.last_used_at,
        )
        for k in keys
    ]


@router.post("", response_model=CreateKeyResponse, status_code=201)
async def create_key(
    body:    CreateKeyRequest,
    request: Request,
    db:      AsyncSession = Depends(get_db_session),
):
    """Create an additional API key for the authenticated user."""
    user_id = _get_user_id_from_request(request)

    count_result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user_id, ApiKey.is_active == True)  # noqa
    )
    if len(count_result.scalars().all()) >= MAX_KEYS_PER_USER:
        raise HTTPException(
            status_code=409,
            detail=f"Maximum {MAX_KEYS_PER_USER} active keys allowed. Revoke one first.",
        )

    raw_key, key_hash, key_prefix = _generate_key()
    api_key = ApiKey(
        id=str(uuid.uuid4()),
        user_id=user_id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=body.name,
        is_active=True,
    )
    db.add(api_key)
    await db.commit()

    logger.info("keys.create: issued key %s for user %s", key_prefix, user_id)

    return CreateKeyResponse(
        message="New API key created. Copy it now — it will not be shown again.",
        api_key=raw_key,
        key_prefix=key_prefix,
    )


@router.delete("/{key_id}", status_code=204)
async def revoke_key(
    key_id:  str,
    request: Request,
    db:      AsyncSession = Depends(get_db_session),
):
    """Revoke (soft-delete) an API key. The key stops working immediately."""
    user_id = _get_user_id_from_request(request)

    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="Key not found.")

    api_key.is_active = False
    await db.commit()
    logger.info("keys.revoke: revoked key %s for user %s", key_id, user_id)
