"""
Stripe checkout and webhook handling
"""
import os
import stripe
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.models import User

# Stripe configuration
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
STRIPE_PRO_PRICE_ID = os.getenv("STRIPE_PRO_PRICE_ID")
STRIPE_BUSINESS_PRICE_ID = os.getenv("STRIPE_BUSINESS_PRICE_ID")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


async def create_checkout_session(db: AsyncSession, api_key: str, tier: str) -> str:
    """
    Create Stripe checkout session for user upgrade
    Returns checkout URL
    """
    # Validate tier
    if tier not in ["pro", "business"]:
        raise HTTPException(status_code=400, detail="Invalid tier. Must be 'pro' or 'business'")

    # Find user
    result = await db.execute(
        select(User).where(User.buzzposter_api_key == api_key)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Select price ID based on tier
    price_id = STRIPE_PRO_PRICE_ID if tier == "pro" else STRIPE_BUSINESS_PRICE_ID

    if not price_id:
        raise HTTPException(status_code=500, detail="Stripe price ID not configured")

    try:
        # Create checkout session
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],
            mode="subscription",
            success_url=f"{BASE_URL}/onboarding?upgraded=true",
            cancel_url=f"{BASE_URL}/billing?canceled=true",
            client_reference_id=api_key,  # Pass API key to identify user in webhook
            customer_email=user.email,
            metadata={
                "api_key": api_key,
                "tier": tier,
            }
        )

        return checkout_session.url

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=500, detail=f"Stripe error: {str(e)}")


async def handle_checkout_completed(db: AsyncSession, session: dict) -> None:
    """
    Handle successful checkout completion
    Update user tier in database
    """
    # Extract API key from metadata or client_reference_id
    api_key = session.get("metadata", {}).get("api_key") or session.get("client_reference_id")
    tier = session.get("metadata", {}).get("tier")

    if not api_key or not tier:
        print(f"Warning: Missing api_key or tier in checkout session {session.get('id')}")
        return

    # Find and update user
    result = await db.execute(
        select(User).where(User.buzzposter_api_key == api_key)
    )
    user = result.scalar_one_or_none()

    if not user:
        print(f"Warning: User not found for api_key {api_key}")
        return

    user.tier = tier
    await db.commit()
    print(f"User {user.email} upgraded to {tier} tier")


async def verify_webhook_signature(request: Request) -> dict:
    """
    Verify Stripe webhook signature and return event
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
        return event
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
