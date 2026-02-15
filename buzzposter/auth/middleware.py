"""
Authentication middleware for API key validation and rate limiting
"""
from datetime import datetime, timedelta
from fastapi import HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.models import User, UsageLog


class UserContext:
    """User context passed to tool handlers"""
    def __init__(self, user: User, db: AsyncSession):
        self.user = user
        self.db = db
        self.tier = user.tier
        self.late_token = user.late_oauth_token
        self.late_refresh_token = user.late_refresh_token


async def validate_api_key(api_key: str, db: AsyncSession) -> UserContext:
    """
    Validate API key and return user context
    Raises HTTPException if invalid or rate limited
    """
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    if not api_key.startswith("bp_"):
        raise HTTPException(status_code=401, detail="Invalid API key format")

    # Find user by API key
    result = await db.execute(
        select(User).where(User.buzzposter_api_key == api_key)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return UserContext(user, db)


async def check_rate_limit(user_context: UserContext, tool_name: str) -> None:
    """
    Check if user has exceeded their rate limit
    Raises HTTPException if limit exceeded
    """
    tier = user_context.tier

    # Define tier limits
    tier_limits = {
        "free": 50,
        "pro": 500,
        "business": None,  # Unlimited
    }

    limit = tier_limits.get(tier)

    # Business tier has no limits
    if limit is None:
        return

    # Count usage today
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    result = await user_context.db.execute(
        select(func.count(UsageLog.id))
        .where(UsageLog.user_id == user_context.user.id)
        .where(UsageLog.timestamp >= today_start)
    )
    usage_count = result.scalar()

    if usage_count >= limit:
        upgrade_message = (
            "Daily limit reached. "
            "Upgrade to Pro ($49/mo) for 500 calls/day or Business ($149/mo) for unlimited. "
            "Visit your billing page to upgrade."
        )
        raise HTTPException(status_code=429, detail=upgrade_message)


async def check_feature_access(user_context: UserContext, feature: str) -> None:
    """
    Check if user's tier has access to a specific feature
    Raises HTTPException if access denied
    """
    tier = user_context.tier

    # Feature access matrix
    access_matrix = {
        "newsapi_search": ["pro", "business"],
        "custom_feeds": ["pro", "business"],
        "social_posting": ["pro", "business"],
        "unlimited_topics": ["pro", "business"],
        "media_upload": ["pro", "business"],
    }

    allowed_tiers = access_matrix.get(feature, [])

    if allowed_tiers and tier not in allowed_tiers:
        raise HTTPException(
            status_code=403,
            detail=f"This feature requires Pro or Business tier. Upgrade to access."
        )


async def log_usage(user_context: UserContext, tool_name: str) -> None:
    """Log tool usage for the user"""
    usage_log = UsageLog(
        user_id=user_context.user.id,
        tool_name=tool_name,
        timestamp=datetime.utcnow()
    )
    user_context.db.add(usage_log)
    await user_context.db.commit()


async def get_user_from_request(request: Request, db: AsyncSession) -> UserContext:
    """
    Extract and validate API key from request headers
    Used by MCP endpoints
    """
    auth_header = request.headers.get("Authorization")

    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")

    api_key = auth_header.replace("Bearer ", "")
    return await validate_api_key(api_key, db)
