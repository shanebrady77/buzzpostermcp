"""
Late.dev OAuth flow implementation
"""
import os
import httpx
from urllib.parse import urlencode
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.models import User


# Late.dev OAuth configuration
LATE_CLIENT_ID = os.getenv("LATE_CLIENT_ID")
LATE_CLIENT_SECRET = os.getenv("LATE_CLIENT_SECRET")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# Late.dev OAuth endpoints (from their docs)
LATE_AUTHORIZE_URL = "https://app.getlate.dev/oauth/authorize"
LATE_TOKEN_URL = "https://getlate.dev/api/v1/oauth/token"


def get_authorization_url(api_key: str) -> str:
    """
    Generate Late.dev OAuth authorization URL
    Pass BuzzPoster API key as state for callback association
    """
    params = {
        "client_id": LATE_CLIENT_ID,
        "redirect_uri": f"{BASE_URL}/auth/late/callback",
        "response_type": "code",
        "state": api_key,  # Pass API key as state
        "scope": "read write",  # Request necessary scopes
    }
    return f"{LATE_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> dict:
    """
    Exchange authorization code for access token
    Returns dict with access_token and refresh_token
    """
    async with httpx.AsyncClient() as client:
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
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to exchange code for token: {str(e)}"
            )


async def refresh_access_token(refresh_token: str) -> dict:
    """
    Refresh expired access token using refresh token
    Returns dict with new access_token and refresh_token
    """
    async with httpx.AsyncClient() as client:
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
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to refresh token: {str(e)}"
            )


async def save_tokens(db: AsyncSession, api_key: str, access_token: str, refresh_token: str) -> None:
    """
    Save OAuth tokens to user record
    """
    result = await db.execute(
        select(User).where(User.buzzposter_api_key == api_key)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.late_oauth_token = access_token
    user.late_refresh_token = refresh_token
    await db.commit()


async def get_connected_accounts(access_token: str) -> dict:
    """
    Fetch connected social accounts from Late.dev
    Returns list of connected platforms
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "https://getlate.dev/api/v1/accounts",
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
    Check if user has connected their Late account and which platforms
    """
    result = await db.execute(
        select(User).where(User.buzzposter_api_key == api_key)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.late_oauth_token:
        return {
            "connected": False,
            "accounts": []
        }

    try:
        accounts = await get_connected_accounts(user.late_oauth_token)
        return {
            "connected": True,
            "accounts": accounts
        }
    except HTTPException:
        # Token might be expired, try to refresh
        if user.late_refresh_token:
            try:
                tokens = await refresh_access_token(user.late_refresh_token)
                await save_tokens(db, api_key, tokens["access_token"], tokens["refresh_token"])
                accounts = await get_connected_accounts(tokens["access_token"])
                return {
                    "connected": True,
                    "accounts": accounts
                }
            except HTTPException:
                return {
                    "connected": False,
                    "accounts": [],
                    "error": "Token expired, please reconnect"
                }
        return {
            "connected": False,
            "accounts": [],
            "error": "Token invalid, please reconnect"
        }
