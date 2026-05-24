"""
Stripe billing routes.

GET   /api/v1/billing/usage      — current period usage + plan info (authenticated)
POST  /api/v1/billing/checkout   — create a Stripe Checkout session to upgrade plan
POST  /api/v1/billing/portal     — create a Stripe Customer Portal session to manage sub
POST  /api/v1/billing/webhook    — Stripe webhook (public, verified by signature)

Stripe env vars required (set in Railway / Render dashboard — never commit):
    STRIPE_SECRET_KEY       — sk_live_... or sk_test_...
    STRIPE_WEBHOOK_SECRET   — whsec_...
    STRIPE_PUBLISHABLE_KEY  — pk_live_... or pk_test_...
    APP_BASE_URL            — e.g. https://api.yourdomain.com (for redirect URLs)

Price IDs — create these in the Stripe dashboard and add to .env:
    STRIPE_PRICE_STARTER    — price_...
    STRIPE_PRICE_PRO        — price_...
    STRIPE_PRICE_TEAM       — price_...
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db_session
from app.models.db.usage_event import UsageEvent
from app.models.db.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/billing", tags=["billing"])

PLAN_LIMITS = {
    "free": 1_000,
    "starter": 10_000,
    "pro": 50_000,
    "team": 200_000,
    "enterprise": None,
}

PLAN_PRICES = {
    "starter": {"label": "Starter — $29/mo", "monthly": 2900},
    "pro": {"label": "Pro — $99/mo", "monthly": 9900},
    "team": {"label": "Team — $299/mo", "monthly": 29900},
}


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class UsageResponse(BaseModel):
    user_id: str
    email: str
    plan: str
    queries_used: int
    queries_limit: Optional[int]  # None = unlimited
    period_start: datetime
    period_end: datetime
    upgrade_options: list[dict]


class CheckoutRequest(BaseModel):
    plan: str  # "starter" | "pro" | "team"


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalResponse(BaseModel):
    portal_url: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _stripe():
    """Lazy-import stripe so the app starts without it if not configured."""
    try:
        import stripe as _stripe

        _stripe.api_key = settings.stripe_secret_key
        return _stripe
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Stripe is not installed. Run: pip install stripe",
        )


def _require_user(request: Request) -> tuple[str, str, str]:
    """Return (user_id, user_email, user_plan) from request.state or raise 401."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return (
        user_id,
        getattr(request.state, "user_email", ""),
        getattr(request.state, "user_plan", "free"),
    )


async def _count_this_month(user_id: str, db: AsyncSession) -> int:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(UsageEvent.id)).where(
            and_(
                UsageEvent.user_id == user_id,
                UsageEvent.created_at >= month_start,
                UsageEvent.endpoint.startswith("/api/v1/search"),
            )
        )
    )
    return result.scalar_one() or 0


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Return current plan + usage for the authenticated user."""
    user_id, email, plan = _require_user(request)
    used = await _count_this_month(user_id, db)
    limit = PLAN_LIMITS.get(plan)

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Next month start
    if now.month == 12:
        period_end = now.replace(
            year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    else:
        period_end = now.replace(
            month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
        )

    upgrade_options = [
        {
            "plan": p,
            "label": PLAN_PRICES[p]["label"],
            "limit": PLAN_LIMITS[p],
        }
        for p in ("starter", "pro", "team")
        if p != plan
    ]

    return UsageResponse(
        user_id=user_id,
        email=email,
        plan=plan,
        queries_used=used,
        queries_limit=limit,
        period_start=month_start,
        period_end=period_end,
        upgrade_options=upgrade_options,
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Create a Stripe Checkout session to upgrade to a paid plan."""
    user_id, email, current_plan = _require_user(request)

    if body.plan not in PLAN_PRICES:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {body.plan}")

    price_id = getattr(settings, f"stripe_price_{body.plan}", None)
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail=f"STRIPE_PRICE_{body.plan.upper()} is not configured.",
        )

    stripe = _stripe()

    # Get or create Stripe customer
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if not user.stripe_customer_id:
        customer = stripe.Customer.create(email=email, metadata={"user_id": user_id})
        user.stripe_customer_id = customer.id
        await db.commit()

    base_url = settings.app_base_url.rstrip("/")
    session = stripe.checkout.Session.create(
        customer=user.stripe_customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{base_url}/dashboard#billing?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base_url}/dashboard#billing",
        metadata={"user_id": user_id, "plan": body.plan},
        allow_promotion_codes=True,
    )

    logger.info("billing.checkout: created session for user %s -> plan %s", user_id, body.plan)
    return CheckoutResponse(checkout_url=session.url)


@router.post("/portal", response_model=PortalResponse)
async def create_portal(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Create a Stripe Customer Portal session so the user can manage their subscription."""
    user_id, email, _ = _require_user(request)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="No billing account found. Subscribe via /api/v1/billing/checkout first.",
        )

    stripe = _stripe()
    base_url = settings.app_base_url.rstrip("/")
    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=f"{base_url}/dashboard#billing",
    )

    logger.info("billing.portal: created portal session for user %s", user_id)
    return PortalResponse(portal_url=session.url)


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Stripe webhook — verifies signature and handles subscription lifecycle events.
    Configure in Stripe dashboard: https://dashboard.stripe.com/webhooks

    Events handled:
      checkout.session.completed      → upgrade plan
      customer.subscription.updated   → sync plan change
      customer.subscription.deleted   → downgrade to free
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    stripe = _stripe()
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except stripe.error.SignatureVerificationError:
        logger.warning("billing.webhook: invalid Stripe signature")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error("billing.webhook: failed to parse event: %s", e)
        raise HTTPException(status_code=400, detail="Malformed event")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = data.get("metadata", {}).get("user_id")
        plan = data.get("metadata", {}).get("plan")
        sub_id = data.get("subscription")
        if user_id and plan:
            await _update_user_plan(db, user_id=user_id, plan=plan, sub_id=sub_id)

    elif event_type == "customer.subscription.updated":
        await _sync_subscription(db, subscription=data)

    elif event_type == "customer.subscription.deleted":
        await _sync_subscription(db, subscription=data, force_free=True)

    else:
        logger.debug("billing.webhook: unhandled event type %s", event_type)

    return JSONResponse({"status": "ok"})


# ── Webhook helpers ───────────────────────────────────────────────────────────


async def _update_user_plan(
    db: AsyncSession, *, user_id: str, plan: str, sub_id: str | None
) -> None:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning("billing: user %s not found for plan update", user_id)
        return
    user.plan = plan
    if sub_id:
        user.stripe_subscription_id = sub_id
    await db.commit()
    logger.info("billing: updated user %s -> plan %s", user_id, plan)


_PRICE_TO_PLAN: dict[str, str] = {}  # populated lazily from settings


async def _sync_subscription(
    db: AsyncSession, *, subscription: dict, force_free: bool = False
) -> None:
    """Map a Stripe subscription object back to a user and sync plan."""
    stripe_customer_id = subscription.get("customer")
    if not stripe_customer_id:
        return

    result = await db.execute(select(User).where(User.stripe_customer_id == stripe_customer_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning("billing: no user found for Stripe customer %s", stripe_customer_id)
        return

    if force_free or subscription.get("status") in ("canceled", "unpaid", "past_due"):
        user.plan = "free"
        user.stripe_subscription_id = None
        await db.commit()
        logger.info("billing: downgraded user %s to free (sub %s)", user.id, subscription.get("id"))
        return

    # Determine new plan from the price ID on the subscription
    items = subscription.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id", "")
        plan = _resolve_plan_from_price(price_id)
        user.plan = plan
        user.stripe_subscription_id = subscription.get("id")
        await db.commit()
        logger.info("billing: synced user %s -> plan %s", user.id, plan)


def _resolve_plan_from_price(price_id: str) -> str:
    """Map a Stripe price ID back to a plan name using settings."""
    for plan in ("starter", "pro", "team", "enterprise"):
        if getattr(settings, f"stripe_price_{plan}", None) == price_id:
            return plan
    logger.warning("billing: unknown price_id %s -- defaulting to free", price_id)
    return "free"
