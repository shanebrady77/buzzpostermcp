"""
Late.dev OAuth flow implementation
"""
import os
import secrets
import httpx
from datetime import datetime, timedelta
from urllib.parse import urlencode
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.models import User


# Late.dev OAuth configuration
LATE_CLIENT_ID = os.getenv("LATE_CLIENT_ID")
LATE_CLIENT_SECRET = os.getenv("LATE_CLIENT_SECRET")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# Late.dev OAuth endpoints
LATE_AUTHORIZE_URL = "https://app.getlate.dev/oauth/authorize"
LATE_TOKEN_URL = "https://getlate.dev/api/v1/oauth/token"
LATE_API_BASE = "https://getlate.dev/api/v1"


async def generate_oauth_state(db: AsyncSession, api_key: str) -> str:
    """
    Generate a secure random state parameter and store it on the user record.
    This prevents CSRF attacks and avoids leaking the API key in the OAuth URL.
    """
    state = secrets.token_urlsafe(32)

    result = await db.execute(
        select(User).where(User.buzzposter_api_key == api_key)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.late_oauth_state = state
    await db.commit()

    return state


async def resolve_oauth_state(db: AsyncSession, state: str) -> str:
    """
    Look up the API key associated with an OAuth state parameter.
    Clears the state after use (one-time use).
    Returns the API key.
    """
    result = await db.execute(
        select(User).where(User.late_oauth_state == state)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    # Clear state (one-time use)
    user.late_oauth_state = None
    await db.commit()

    return user.buzzposter_api_key


def get_authorization_url(state: str) -> str:
    """
    Generate Late.dev OAuth authorization URL using a secure state token.
    """
    params = {
        "client_id": LATE_CLIENT_ID,
        "redirect_uri": f"{BASE_URL}/auth/late/callback",
        "response_type": "code",
        "state": state,
        "scope": "read write",
    }
    return f"{LATE_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> dict:
    """
    Exchange authorization code for access token.
    Returns dict with access_token, refresh_token, and expires_in.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                LATE_TOKEN_URL,
                json={
                    "client_id": LATE_CLIENT_ID,
                    "client_secret": LATE_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": f"{BASE_URL}/auth/late/callback",
                }
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Late.dev token exchange failed ({e.response.status_code}): {e.response.text}"
            )
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to connect to Late.dev: {str(e)}"
            )


async def refresh_access_token(refresh_token: str) -> dict:
    """
    Refresh expired access token using refresh token.
    Returns dict with new access_token, refresh_token, and expires_in.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                LATE_TOKEN_URL,
                json={
                    "client_id": LATE_CLIENT_ID,
                    "client_secret": LATE_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                }
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Late.dev token refresh failed ({e.response.status_code}): {e.response.text}"
            )
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to connect to Late.dev: {str(e)}"
            )


async def save_tokens(db: AsyncSession, api_key: str, access_token: str, refresh_token: str, expires_in: int = None) -> None:
    """
    Save OAuth tokens and expiry to user record.
    """
    result = await db.execute(
        select(User).where(User.buzzposter_api_key == api_key)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.late_oauth_token = access_token
    user.late_refresh_token = refresh_token

    if expires_in:
        user.late_token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    else:
        # Default to 1 hour if not provided
        user.late_token_expires_at = datetime.utcnow() + timedelta(hours=1)

    await db.commit()


async def clear_tokens(db: AsyncSession, api_key: str) -> None:
    """
    Clear Late.dev OAuth tokens from user record (disconnect).
    """
    result = await db.execute(
        select(User).where(User.buzzposter_api_key == api_key)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.late_oauth_token = None
    user.late_refresh_token = None
    user.late_token_expires_at = None
    await db.commit()


async def validate_token(access_token: str) -> dict:
    """
    Validate that an access token actually works by making a test API call.
    Returns the accounts response if valid.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(
                f"{LATE_API_BASE}/accounts",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError:
            return None


async def get_connected_accounts(access_token: str) -> dict:
    """
    Fetch connected social accounts from Late.dev.
    Returns list of connected platforms.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(
                f"{LATE_API_BASE}/accounts",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch connected accounts: {str(e)}"
            )


async def check_connection_status(db: AsyncSession, api_key: str) -> dict:
    """
    Check if user has connected their Late account and which platforms.
    Includes connect URL for easy onboarding.
    """
    result = await db.execute(
        select(User).where(User.buzzposter_api_key == api_key)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    connect_url = f"{BASE_URL}/auth/late/connect?api_key={api_key}"

    if not user.late_oauth_token:
        return {
            "connected": False,
            "accounts": [],
            "connect_url": connect_url,
        }

    # Check if token is about to expire (within 5 minutes)
    if user.late_token_expires_at and user.late_token_expires_at < datetime.utcnow() + timedelta(minutes=5):
        # Proactively refresh
        if user.late_refresh_token:
            try:
                tokens = await refresh_access_token(user.late_refresh_token)
                await save_tokens(
                    db, api_key,
                    tokens["access_token"],
                    tokens["refresh_token"],
                    tokens.get("expires_in"),
                )
                user.late_oauth_token = tokens["access_token"]
            except HTTPException:
                return {
                    "connected": False,
                    "accounts": [],
                    "connect_url": connect_url,
                    "error": "Token expired and refresh failed. Please reconnect.",
                }

    try:
        accounts = await get_connected_accounts(user.late_oauth_token)
        return {
            "connected": True,
            "accounts": accounts,
            "connect_url": connect_url,
        }
    except HTTPException:
        # Token might be expired, try to refresh
        if user.late_refresh_token:
            try:
                tokens = await refresh_access_token(user.late_refresh_token)
                await save_tokens(
                    db, api_key,
                    tokens["access_token"],
                    tokens["refresh_token"],
                    tokens.get("expires_in"),
                )
                accounts = await get_connected_accounts(tokens["access_token"])
                return {
                    "connected": True,
                    "accounts": accounts,
                    "connect_url": connect_url,
                }
            except HTTPException:
                # Refresh also failed - clear stale tokens
                await clear_tokens(db, api_key)
                return {
                    "connected": False,
                    "accounts": [],
                    "connect_url": connect_url,
                    "error": "Token expired and refresh failed. Please reconnect.",
                }
        # No refresh token available
        await clear_tokens(db, api_key)
        return {
            "connected": False,
            "accounts": [],
            "connect_url": connect_url,
            "error": "Token invalid. Please reconnect.",
        }
