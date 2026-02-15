"""
Newsletter and CMS integration tools for BuzzPoster
Supports: Beehiiv, Kit/ConvertKit, Mailchimp, WordPress, Ghost, Webflow
"""
import os
import json
import base64
import httpx
import hashlib
import hmac
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy import select

from ..auth.middleware import UserContext, check_rate_limit, check_feature_access, log_usage
from ..db.models import UserIntegration


# =============================================================================
# Helper Functions
# =============================================================================

async def get_integration(user_ctx: UserContext, platform: str) -> Optional[UserIntegration]:
    """Get user's integration for a specific platform"""
    stmt = select(UserIntegration).where(
        UserIntegration.user_id == user_ctx.user.id,
        UserIntegration.platform == platform
    )
    result = await user_ctx.db.execute(stmt)
    return result.scalar_one_or_none()


# =============================================================================
# Beehiiv Integration
# =============================================================================

async def buzzposter_draft_beehiiv(
    user_ctx: UserContext,
    title: str,
    content: str,
    preview_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a draft post in Beehiiv

    Args:
        user_ctx: User context
        title: Post title
        content: Post content (HTML)
        preview_text: Optional preview text

    Returns:
        Dict with post info or error
    """
    await check_rate_limit(user_ctx, "buzzposter_draft_beehiiv")
    await check_feature_access(user_ctx, "integrations")

    integration = await get_integration(user_ctx, "beehiiv")
    if not integration:
        return {"error": "Beehiiv not connected. Use buzzposter_connect_platform first."}

    pub_id = integration.metadata.get("publication_id") if integration.metadata else None
    if not pub_id:
        return {"error": "Beehiiv publication ID not configured"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://api.beehiiv.com/v2/publications/{pub_id}/posts",
                headers={"Authorization": f"Bearer {integration.access_token}"},
                json={
                    "title": title,
                    "content_html": content,
                    "status": "draft",
                    "preview_text": preview_text or title[:100]
                }
            )
            response.raise_for_status()
            data = response.json()

        await log_usage(user_ctx, "buzzposter_draft_beehiiv")

        return {
            "success": True,
            "platform": "beehiiv",
            "status": "draft",
            "post_id": data.get("data", {}).get("id"),
            "title": title
        }

    except httpx.HTTPError as e:
        return {"error": f"Beehiiv API error: {str(e)}"}


async def buzzposter_publish_beehiiv(
    user_ctx: UserContext,
    title: str,
    content: str,
    preview_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Publish a post to Beehiiv (creates as confirmed, ready to send)
    Note: Actual sending requires Enterprise plan

    Args:
        user_ctx: User context
        title: Post title
        content: Post content (HTML)
        preview_text: Optional preview text

    Returns:
        Dict with post info or error
    """
    await check_rate_limit(user_ctx, "buzzposter_publish_beehiiv")
    await check_feature_access(user_ctx, "integrations")

    integration = await get_integration(user_ctx, "beehiiv")
    if not integration:
        return {"error": "Beehiiv not connected. Use buzzposter_connect_platform first."}

    pub_id = integration.metadata.get("publication_id") if integration.metadata else None
    if not pub_id:
        return {"error": "Beehiiv publication ID not configured"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://api.beehiiv.com/v2/publications/{pub_id}/posts",
                headers={"Authorization": f"Bearer {integration.access_token}"},
                json={
                    "title": title,
                    "content_html": content,
                    "status": "confirmed",
                    "preview_text": preview_text or title[:100]
                }
            )
            response.raise_for_status()
            data = response.json()

        await log_usage(user_ctx, "buzzposter_publish_beehiiv")

        return {
            "success": True,
            "platform": "beehiiv",
            "status": "confirmed",
            "post_id": data.get("data", {}).get("id"),
            "title": title,
            "note": "Post created as confirmed. Sending requires Enterprise plan."
        }

    except httpx.HTTPError as e:
        return {"error": f"Beehiiv API error: {str(e)}"}


# =============================================================================
# Kit/ConvertKit Integration
# =============================================================================

async def buzzposter_draft_kit(
    user_ctx: UserContext,
    subject: str,
    content: str,
    preview_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a draft broadcast in Kit/ConvertKit

    Args:
        user_ctx: User context
        subject: Email subject
        content: Email content (HTML)
        preview_text: Optional preview text

    Returns:
        Dict with broadcast info or error
    """
    await check_rate_limit(user_ctx, "buzzposter_draft_kit")
    await check_feature_access(user_ctx, "integrations")

    integration = await get_integration(user_ctx, "kit")
    if not integration:
        return {"error": "Kit not connected. Use buzzposter_connect_platform first."}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.kit.com/v4/broadcasts",
                headers={"Authorization": f"Bearer {integration.access_token}"},
                json={
                    "subject": subject,
                    "content": content,
                    "preview_text": preview_text or subject[:100],
                    "published": False
                }
            )
            response.raise_for_status()
            data = response.json()

        await log_usage(user_ctx, "buzzposter_draft_kit")

        return {
            "success": True,
            "platform": "kit",
            "status": "draft",
            "broadcast_id": data.get("broadcast", {}).get("id"),
            "subject": subject
        }

    except httpx.HTTPError as e:
        return {"error": f"Kit API error: {str(e)}"}


async def buzzposter_publish_kit(
    user_ctx: UserContext,
    subject: str,
    content: str,
    preview_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create and send a broadcast in Kit/ConvertKit

    Args:
        user_ctx: User context
        subject: Email subject
        content: Email content (HTML)
        preview_text: Optional preview text

    Returns:
        Dict with broadcast info or error
    """
    await check_rate_limit(user_ctx, "buzzposter_publish_kit")
    await check_feature_access(user_ctx, "integrations")

    integration = await get_integration(user_ctx, "kit")
    if not integration:
        return {"error": "Kit not connected. Use buzzposter_connect_platform first."}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.kit.com/v4/broadcasts",
                headers={"Authorization": f"Bearer {integration.access_token}"},
                json={
                    "subject": subject,
                    "content": content,
                    "preview_text": preview_text or subject[:100],
                    "published": True
                }
            )
            response.raise_for_status()
            data = response.json()

        await log_usage(user_ctx, "buzzposter_publish_kit")

        return {
            "success": True,
            "platform": "kit",
            "status": "sent",
            "broadcast_id": data.get("broadcast", {}).get("id"),
            "subject": subject
        }

    except httpx.HTTPError as e:
        return {"error": f"Kit API error: {str(e)}"}


# =============================================================================
# Mailchimp Integration
# =============================================================================

async def buzzposter_draft_mailchimp(
    user_ctx: UserContext,
    subject: str,
    content: str,
    preview_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a draft campaign in Mailchimp

    Args:
        user_ctx: User context
        subject: Email subject
        content: Email content (HTML)
        preview_text: Optional preview text

    Returns:
        Dict with campaign info or error
    """
    await check_rate_limit(user_ctx, "buzzposter_draft_mailchimp")
    await check_feature_access(user_ctx, "integrations")

    integration = await get_integration(user_ctx, "mailchimp")
    if not integration:
        return {"error": "Mailchimp not connected. Use buzzposter_connect_platform first."}

    list_id = integration.metadata.get("list_id") if integration.metadata else None
    if not list_id:
        return {"error": "Mailchimp list ID not configured"}

    # Extract DC from API key (format: key-dc)
    dc = integration.access_token.split("-")[-1] if "-" in integration.access_token else "us1"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Create campaign
            auth_header = base64.b64encode(f"anystring:{integration.access_token}".encode()).decode()

            campaign_response = await client.post(
                f"https://{dc}.api.mailchimp.com/3.0/campaigns",
                headers={"Authorization": f"Basic {auth_header}"},
                json={
                    "type": "regular",
                    "recipients": {"list_id": list_id},
                    "settings": {
                        "subject_line": subject,
                        "preview_text": preview_text or subject[:100],
                        "from_name": integration.metadata.get("from_name", "Newsletter"),
                        "reply_to": integration.metadata.get("reply_to", "noreply@example.com")
                    }
                }
            )
            campaign_response.raise_for_status()
            campaign_data = campaign_response.json()
            campaign_id = campaign_data["id"]

            # Set content
            content_response = await client.put(
                f"https://{dc}.api.mailchimp.com/3.0/campaigns/{campaign_id}/content",
                headers={"Authorization": f"Basic {auth_header}"},
                json={"html": content}
            )
            content_response.raise_for_status()

        await log_usage(user_ctx, "buzzposter_draft_mailchimp")

        return {
            "success": True,
            "platform": "mailchimp",
            "status": "draft",
            "campaign_id": campaign_id,
            "subject": subject
        }

    except httpx.HTTPError as e:
        return {"error": f"Mailchimp API error: {str(e)}"}


async def buzzposter_publish_mailchimp(
    user_ctx: UserContext,
    subject: str,
    content: str,
    preview_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create and send a campaign in Mailchimp

    Args:
        user_ctx: User context
        subject: Email subject
        content: Email content (HTML)
        preview_text: Optional preview text

    Returns:
        Dict with campaign info or error
    """
    await check_rate_limit(user_ctx, "buzzposter_publish_mailchimp")
    await check_feature_access(user_ctx, "integrations")

    # First create draft
    draft_result = await buzzposter_draft_mailchimp(user_ctx, subject, content, preview_text)
    if "error" in draft_result:
        return draft_result

    campaign_id = draft_result["campaign_id"]
    integration = await get_integration(user_ctx, "mailchimp")
    dc = integration.access_token.split("-")[-1] if "-" in integration.access_token else "us1"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            auth_header = base64.b64encode(f"anystring:{integration.access_token}".encode()).decode()

            # Send campaign
            send_response = await client.post(
                f"https://{dc}.api.mailchimp.com/3.0/campaigns/{campaign_id}/actions/send",
                headers={"Authorization": f"Basic {auth_header}"}
            )
            send_response.raise_for_status()

        await log_usage(user_ctx, "buzzposter_publish_mailchimp")

        return {
            "success": True,
            "platform": "mailchimp",
            "status": "sent",
            "campaign_id": campaign_id,
            "subject": subject
        }

    except httpx.HTTPError as e:
        return {"error": f"Mailchimp send error: {str(e)}"}


# =============================================================================
# WordPress Integration
# =============================================================================

async def buzzposter_draft_wordpress(
    user_ctx: UserContext,
    title: str,
    content: str
) -> Dict[str, Any]:
    """
    Create a draft post in WordPress

    Args:
        user_ctx: User context
        title: Post title
        content: Post content (HTML)

    Returns:
        Dict with post info or error
    """
    await check_rate_limit(user_ctx, "buzzposter_draft_wordpress")
    await check_feature_access(user_ctx, "integrations")

    integration = await get_integration(user_ctx, "wordpress")
    if not integration:
        return {"error": "WordPress not connected. Use buzzposter_connect_platform first."}

    site_url = integration.metadata.get("site_url") if integration.metadata else None
    username = integration.metadata.get("username") if integration.metadata else None

    if not site_url or not username:
        return {"error": "WordPress site URL or username not configured"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # WordPress uses Application Password for Basic auth
            auth_header = base64.b64encode(f"{username}:{integration.access_token}".encode()).decode()

            response = await client.post(
                f"{site_url.rstrip('/')}/wp-json/wp/v2/posts",
                headers={"Authorization": f"Basic {auth_header}"},
                json={
                    "title": title,
                    "content": content,
                    "status": "draft"
                }
            )
            response.raise_for_status()
            data = response.json()

        await log_usage(user_ctx, "buzzposter_draft_wordpress")

        return {
            "success": True,
            "platform": "wordpress",
            "status": "draft",
            "post_id": data.get("id"),
            "title": title,
            "url": data.get("link")
        }

    except httpx.HTTPError as e:
        return {"error": f"WordPress API error: {str(e)}"}


async def buzzposter_publish_wordpress(
    user_ctx: UserContext,
    title: str,
    content: str
) -> Dict[str, Any]:
    """
    Create and publish a post in WordPress

    Args:
        user_ctx: User context
        title: Post title
        content: Post content (HTML)

    Returns:
        Dict with post info or error
    """
    await check_rate_limit(user_ctx, "buzzposter_publish_wordpress")
    await check_feature_access(user_ctx, "integrations")

    integration = await get_integration(user_ctx, "wordpress")
    if not integration:
        return {"error": "WordPress not connected. Use buzzposter_connect_platform first."}

    site_url = integration.metadata.get("site_url") if integration.metadata else None
    username = integration.metadata.get("username") if integration.metadata else None

    if not site_url or not username:
        return {"error": "WordPress site URL or username not configured"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            auth_header = base64.b64encode(f"{username}:{integration.access_token}".encode()).decode()

            response = await client.post(
                f"{site_url.rstrip('/')}/wp-json/wp/v2/posts",
                headers={"Authorization": f"Basic {auth_header}"},
                json={
                    "title": title,
                    "content": content,
                    "status": "publish"
                }
            )
            response.raise_for_status()
            data = response.json()

        await log_usage(user_ctx, "buzzposter_publish_wordpress")

        return {
            "success": True,
            "platform": "wordpress",
            "status": "published",
            "post_id": data.get("id"),
            "title": title,
            "url": data.get("link")
        }

    except httpx.HTTPError as e:
        return {"error": f"WordPress API error: {str(e)}"}


# =============================================================================
# Ghost Integration
# =============================================================================

def _generate_ghost_jwt(api_key: str) -> str:
    """Generate JWT for Ghost Admin API"""
    import jwt

    # Split key into ID and SECRET
    key_id, secret = api_key.split(":")

    # Create JWT
    iat = int(datetime.utcnow().timestamp())
    header = {"alg": "HS256", "typ": "JWT", "kid": key_id}
    payload = {
        "iat": iat,
        "exp": iat + 300,  # 5 minutes
        "aud": "/admin/"
    }

    token = jwt.encode(payload, bytes.fromhex(secret), algorithm="HS256", headers=header)
    return token


async def buzzposter_draft_ghost(
    user_ctx: UserContext,
    title: str,
    content: str
) -> Dict[str, Any]:
    """
    Create a draft post in Ghost

    Args:
        user_ctx: User context
        title: Post title
        content: Post content (HTML)

    Returns:
        Dict with post info or error
    """
    await check_rate_limit(user_ctx, "buzzposter_draft_ghost")
    await check_feature_access(user_ctx, "integrations")

    integration = await get_integration(user_ctx, "ghost")
    if not integration:
        return {"error": "Ghost not connected. Use buzzposter_connect_platform first."}

    site_url = integration.metadata.get("site_url") if integration.metadata else None
    if not site_url:
        return {"error": "Ghost site URL not configured"}

    try:
        token = _generate_ghost_jwt(integration.access_token)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{site_url.rstrip('/')}/ghost/api/admin/posts/",
                headers={"Authorization": f"Ghost {token}"},
                json={
                    "posts": [{
                        "title": title,
                        "html": content,
                        "status": "draft"
                    }]
                }
            )
            response.raise_for_status()
            data = response.json()

        await log_usage(user_ctx, "buzzposter_draft_ghost")

        post = data.get("posts", [{}])[0]
        return {
            "success": True,
            "platform": "ghost",
            "status": "draft",
            "post_id": post.get("id"),
            "title": title,
            "url": post.get("url")
        }

    except Exception as e:
        return {"error": f"Ghost API error: {str(e)}"}


async def buzzposter_publish_ghost(
    user_ctx: UserContext,
    title: str,
    content: str
) -> Dict[str, Any]:
    """
    Create and publish a post in Ghost

    Args:
        user_ctx: User context
        title: Post title
        content: Post content (HTML)

    Returns:
        Dict with post info or error
    """
    await check_rate_limit(user_ctx, "buzzposter_publish_ghost")
    await check_feature_access(user_ctx, "integrations")

    integration = await get_integration(user_ctx, "ghost")
    if not integration:
        return {"error": "Ghost not connected. Use buzzposter_connect_platform first."}

    site_url = integration.metadata.get("site_url") if integration.metadata else None
    if not site_url:
        return {"error": "Ghost site URL not configured"}

    try:
        token = _generate_ghost_jwt(integration.access_token)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{site_url.rstrip('/')}/ghost/api/admin/posts/",
                headers={"Authorization": f"Ghost {token}"},
                json={
                    "posts": [{
                        "title": title,
                        "html": content,
                        "status": "published"
                    }]
                }
            )
            response.raise_for_status()
            data = response.json()

        await log_usage(user_ctx, "buzzposter_publish_ghost")

        post = data.get("posts", [{}])[0]
        return {
            "success": True,
            "platform": "ghost",
            "status": "published",
            "post_id": post.get("id"),
            "title": title,
            "url": post.get("url")
        }

    except Exception as e:
        return {"error": f"Ghost API error: {str(e)}"}


# =============================================================================
# Webflow Integration
# =============================================================================

async def buzzposter_draft_webflow(
    user_ctx: UserContext,
    title: str,
    content: str
) -> Dict[str, Any]:
    """
    Create a draft item in Webflow CMS

    Args:
        user_ctx: User context
        title: Post title
        content: Post content (HTML)

    Returns:
        Dict with item info or error
    """
    await check_rate_limit(user_ctx, "buzzposter_draft_webflow")
    await check_feature_access(user_ctx, "integrations")

    integration = await get_integration(user_ctx, "webflow")
    if not integration:
        return {"error": "Webflow not connected. Use buzzposter_connect_platform first."}

    collection_id = integration.metadata.get("collection_id") if integration.metadata else None
    if not collection_id:
        return {"error": "Webflow collection ID not configured"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://api.webflow.com/v2/collections/{collection_id}/items",
                headers={"Authorization": f"Bearer {integration.access_token}"},
                json={
                    "isArchived": False,
                    "isDraft": True,
                    "fieldData": {
                        "name": title,
                        "slug": title.lower().replace(" ", "-")[:100],
                        "post-body": content
                    }
                }
            )
            response.raise_for_status()
            data = response.json()

        await log_usage(user_ctx, "buzzposter_draft_webflow")

        return {
            "success": True,
            "platform": "webflow",
            "status": "draft",
            "item_id": data.get("id"),
            "title": title
        }

    except httpx.HTTPError as e:
        return {"error": f"Webflow API error: {str(e)}"}


async def buzzposter_publish_webflow(
    user_ctx: UserContext,
    title: str,
    content: str
) -> Dict[str, Any]:
    """
    Create and publish an item in Webflow CMS

    Args:
        user_ctx: User context
        title: Post title
        content: Post content (HTML)

    Returns:
        Dict with item info or error
    """
    await check_rate_limit(user_ctx, "buzzposter_publish_webflow")
    await check_feature_access(user_ctx, "integrations")

    integration = await get_integration(user_ctx, "webflow")
    if not integration:
        return {"error": "Webflow not connected. Use buzzposter_connect_platform first."}

    collection_id = integration.metadata.get("collection_id") if integration.metadata else None
    if not collection_id:
        return {"error": "Webflow collection ID not configured"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://api.webflow.com/v2/collections/{collection_id}/items",
                headers={"Authorization": f"Bearer {integration.access_token}"},
                json={
                    "isArchived": False,
                    "isDraft": False,
                    "fieldData": {
                        "name": title,
                        "slug": title.lower().replace(" ", "-")[:100],
                        "post-body": content
                    }
                }
            )
            response.raise_for_status()
            data = response.json()

        await log_usage(user_ctx, "buzzposter_publish_webflow")

        return {
            "success": True,
            "platform": "webflow",
            "status": "published",
            "item_id": data.get("id"),
            "title": title
        }

    except httpx.HTTPError as e:
        return {"error": f"Webflow API error: {str(e)}"}


# =============================================================================
# Connection Management Tools
# =============================================================================

async def buzzposter_connect_platform(
    user_ctx: UserContext,
    platform: str,
    credentials: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Connect a platform by storing credentials

    Args:
        user_ctx: User context
        platform: Platform name (beehiiv, kit, mailchimp, wordpress, ghost, webflow)
        credentials: Platform-specific credentials dict

    Returns:
        Dict with success status or error
    """
    await check_rate_limit(user_ctx, "buzzposter_connect_platform")
    await check_feature_access(user_ctx, "integrations")

    valid_platforms = ["beehiiv", "kit", "mailchimp", "wordpress", "ghost", "webflow"]
    if platform not in valid_platforms:
        return {"error": f"Invalid platform. Must be one of: {', '.join(valid_platforms)}"}

    # Validate required credentials per platform
    required_fields = {
        "beehiiv": ["api_key", "publication_id"],
        "kit": ["api_key"],
        "mailchimp": ["api_key", "list_id"],
        "wordpress": ["site_url", "username", "app_password"],
        "ghost": ["site_url", "admin_api_key"],
        "webflow": ["api_token", "collection_id"]
    }

    for field in required_fields.get(platform, []):
        if field not in credentials:
            return {"error": f"Missing required field: {field}"}

    try:
        # Check if integration already exists
        existing = await get_integration(user_ctx, platform)

        # Prepare integration data
        if platform in ["beehiiv", "kit", "mailchimp", "webflow"]:
            access_token = credentials.get("api_key") or credentials.get("api_token")
            metadata = {k: v for k, v in credentials.items() if k not in ["api_key", "api_token"]}
        elif platform == "wordpress":
            access_token = credentials["app_password"]
            metadata = {"site_url": credentials["site_url"], "username": credentials["username"]}
        elif platform == "ghost":
            access_token = credentials["admin_api_key"]
            metadata = {"site_url": credentials["site_url"]}

        if existing:
            # Update existing integration
            existing.access_token = access_token
            existing.metadata = metadata
            existing.updated_at = datetime.utcnow()
        else:
            # Create new integration
            integration = UserIntegration(
                user_id=user_ctx.user.id,
                platform=platform,
                access_token=access_token,
                metadata=metadata
            )
            user_ctx.db.add(integration)

        await user_ctx.db.commit()
        await log_usage(user_ctx, "buzzposter_connect_platform")

        return {
            "success": True,
            "platform": platform,
            "status": "connected",
            "message": f"{platform.capitalize()} connected successfully"
        }

    except Exception as e:
        return {"error": f"Failed to connect platform: {str(e)}"}


async def buzzposter_list_integrations(user_ctx: UserContext) -> Dict[str, Any]:
    """
    List all connected platforms for the user

    Args:
        user_ctx: User context

    Returns:
        Dict with list of connected platforms
    """
    await check_rate_limit(user_ctx, "buzzposter_list_integrations")

    try:
        stmt = select(UserIntegration).where(UserIntegration.user_id == user_ctx.user.id)
        result = await user_ctx.db.execute(stmt)
        integrations = result.scalars().all()

        await log_usage(user_ctx, "buzzposter_list_integrations")

        return {
            "integrations": [
                {
                    "platform": i.platform,
                    "connected_at": i.created_at.isoformat(),
                    "metadata": i.metadata
                }
                for i in integrations
            ],
            "total": len(integrations)
        }

    except Exception as e:
        return {"error": f"Failed to list integrations: {str(e)}"}
