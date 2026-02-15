"""
Late.dev social media posting tools
"""
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime
from ..auth.middleware import UserContext, check_rate_limit, check_feature_access, log_usage


LATE_API_BASE = "https://getlate.dev/api/v1"


async def _make_late_request(
    user_ctx: UserContext,
    method: str,
    endpoint: str,
    json_data: Optional[Dict] = None,
    params: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Make authenticated request to Late.dev API
    Handles token refresh if needed
    """
    if not user_ctx.late_token:
        return {"error": "Late.dev account not connected. Please connect via /auth/late/connect"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.request(
                method,
                f"{LATE_API_BASE}/{endpoint}",
                headers={"Authorization": f"Bearer {user_ctx.late_token}"},
                json=json_data,
                params=params,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Token expired, try to refresh
                if user_ctx.late_refresh_token:
                    from ..auth.late_oauth import refresh_access_token, save_tokens
                    try:
                        tokens = await refresh_access_token(user_ctx.late_refresh_token)
                        await save_tokens(
                            user_ctx.db,
                            user_ctx.user.buzzposter_api_key,
                            tokens["access_token"],
                            tokens["refresh_token"]
                        )
                        # Retry request with new token
                        response = await client.request(
                            method,
                            f"{LATE_API_BASE}/{endpoint}",
                            headers={"Authorization": f"Bearer {tokens['access_token']}"},
                            json=json_data,
                            params=params,
                        )
                        response.raise_for_status()
                        return response.json()
                    except Exception:
                        return {"error": "Token expired. Please reconnect via /auth/late/connect"}
                return {"error": "Token expired. Please reconnect via /auth/late/connect"}
            return {"error": f"Late.dev API error: {e.response.status_code} - {e.response.text}"}

        except httpx.HTTPError as e:
            return {"error": f"Late.dev request failed: {str(e)}"}


async def buzzposter_list_social_accounts(user_ctx: UserContext) -> Dict[str, Any]:
    """
    List all connected social media accounts
    Requires Pro or Business tier

    Args:
        user_ctx: User context with auth and db

    Returns:
        List of connected social accounts
    """
    await check_rate_limit(user_ctx, "buzzposter_list_social_accounts")
    await check_feature_access(user_ctx, "social_posting")

    result = await _make_late_request(user_ctx, "GET", "accounts")

    if "error" not in result:
        await log_usage(user_ctx, "buzzposter_list_social_accounts")

    return result


async def buzzposter_post(
    user_ctx: UserContext,
    platform: str,
    content: str,
    media_urls: Optional[List[str]] = None,
    account_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Post content to a specific social media platform
    Requires Pro or Business tier

    Args:
        user_ctx: User context with auth and db
        platform: Platform name (twitter, linkedin, facebook, etc.)
        content: Text content to post
        media_urls: Optional list of media URLs to attach
        account_id: Optional specific account ID (if user has multiple accounts for platform)

    Returns:
        Post result with post ID and URL
    """
    await check_rate_limit(user_ctx, "buzzposter_post")
    await check_feature_access(user_ctx, "social_posting")

    post_data = {
        "platform": platform,
        "content": content,
    }

    if media_urls:
        post_data["media_urls"] = media_urls
    if account_id:
        post_data["account_id"] = account_id

    result = await _make_late_request(user_ctx, "POST", "posts", json_data=post_data)

    if "error" not in result:
        await log_usage(user_ctx, "buzzposter_post")

    return result


async def buzzposter_cross_post(
    user_ctx: UserContext,
    platforms: List[str],
    content: str,
    media_urls: Optional[List[str]] = None,
    customize_per_platform: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Post same content to multiple platforms
    Requires Pro or Business tier

    Args:
        user_ctx: User context with auth and db
        platforms: List of platform names
        content: Base text content to post
        media_urls: Optional list of media URLs to attach
        customize_per_platform: Optional dict of platform-specific content overrides

    Returns:
        Results for each platform
    """
    await check_rate_limit(user_ctx, "buzzposter_cross_post")
    await check_feature_access(user_ctx, "social_posting")

    post_data = {
        "platforms": platforms,
        "content": content,
    }

    if media_urls:
        post_data["media_urls"] = media_urls
    if customize_per_platform:
        post_data["customize_per_platform"] = customize_per_platform

    result = await _make_late_request(user_ctx, "POST", "posts/cross-post", json_data=post_data)

    if "error" not in result:
        await log_usage(user_ctx, "buzzposter_cross_post")

    return result


async def buzzposter_schedule_post(
    user_ctx: UserContext,
    platform: str,
    content: str,
    scheduled_at: str,
    media_urls: Optional[List[str]] = None,
    account_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Schedule a post for later
    Requires Pro or Business tier

    Args:
        user_ctx: User context with auth and db
        platform: Platform name
        content: Text content to post
        scheduled_at: ISO 8601 timestamp for when to post
        media_urls: Optional list of media URLs to attach
        account_id: Optional specific account ID

    Returns:
        Scheduled post info with ID
    """
    await check_rate_limit(user_ctx, "buzzposter_schedule_post")
    await check_feature_access(user_ctx, "social_posting")

    post_data = {
        "platform": platform,
        "content": content,
        "scheduled_at": scheduled_at,
    }

    if media_urls:
        post_data["media_urls"] = media_urls
    if account_id:
        post_data["account_id"] = account_id

    result = await _make_late_request(user_ctx, "POST", "posts/schedule", json_data=post_data)

    if "error" not in result:
        await log_usage(user_ctx, "buzzposter_schedule_post")

    return result


async def buzzposter_list_posts(
    user_ctx: UserContext,
    status: Optional[str] = None,
    platform: Optional[str] = None,
    limit: int = 20
) -> Dict[str, Any]:
    """
    List scheduled, published, or draft posts
    Requires Pro or Business tier

    Args:
        user_ctx: User context with auth and db
        status: Filter by status (scheduled, published, draft, failed)
        platform: Filter by platform
        limit: Number of posts to return (default 20)

    Returns:
        List of posts with metadata
    """
    await check_rate_limit(user_ctx, "buzzposter_list_posts")
    await check_feature_access(user_ctx, "social_posting")

    params = {"limit": limit}
    if status:
        params["status"] = status
    if platform:
        params["platform"] = platform

    result = await _make_late_request(user_ctx, "GET", "posts", params=params)

    if "error" not in result:
        await log_usage(user_ctx, "buzzposter_list_posts")

    return result


async def buzzposter_post_analytics(
    user_ctx: UserContext,
    post_id: str
) -> Dict[str, Any]:
    """
    Get engagement analytics for a post
    Requires Pro or Business tier

    Args:
        user_ctx: User context with auth and db
        post_id: ID of the post

    Returns:
        Analytics data (likes, shares, comments, impressions, etc.)
    """
    await check_rate_limit(user_ctx, "buzzposter_post_analytics")
    await check_feature_access(user_ctx, "social_posting")

    result = await _make_late_request(user_ctx, "GET", f"posts/{post_id}/analytics")

    if "error" not in result:
        await log_usage(user_ctx, "buzzposter_post_analytics")

    return result
