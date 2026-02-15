"""
User profile and feed management tools
"""
from typing import List, Dict, Any, Optional
from sqlalchemy import select
from ..db.models import UserFeed, UserProfile
from ..auth.middleware import UserContext, check_rate_limit, check_feature_access, log_usage
from .feeds import buzzposter_get_feed


async def buzzposter_add_feed(
    user_ctx: UserContext,
    feed_url: str,
    feed_name: str,
    topic: Optional[str] = None
) -> Dict[str, Any]:
    """
    Add a custom RSS feed to user's collection
    Requires Pro or Business tier

    Args:
        user_ctx: User context with auth and db
        feed_url: URL of the RSS feed
        feed_name: Display name for the feed
        topic: Optional topic category

    Returns:
        Success message and feed info
    """
    await check_rate_limit(user_ctx, "buzzposter_add_feed")
    await check_feature_access(user_ctx, "custom_feeds")

    # Verify feed is valid by attempting to fetch it
    test_result = await buzzposter_get_feed(user_ctx, feed_url)
    if "error" in test_result:
        return {"error": f"Invalid feed URL: {test_result['error']}"}

    # Check if feed already exists for this user
    result = await user_ctx.db.execute(
        select(UserFeed).where(
            UserFeed.user_id == user_ctx.user.id,
            UserFeed.feed_url == feed_url
        )
    )
    existing_feed = result.scalar_one_or_none()

    if existing_feed:
        return {"error": "Feed already exists in your collection"}

    # Add feed
    user_feed = UserFeed(
        user_id=user_ctx.user.id,
        feed_url=feed_url,
        feed_name=feed_name,
        topic=topic,
    )
    user_ctx.db.add(user_feed)
    await user_ctx.db.commit()

    await log_usage(user_ctx, "buzzposter_add_feed")

    return {
        "success": True,
        "message": f"Added feed: {feed_name}",
        "feed": {
            "id": user_feed.id,
            "name": feed_name,
            "url": feed_url,
            "topic": topic,
        }
    }


async def buzzposter_remove_feed(user_ctx: UserContext, feed_id: int) -> Dict[str, Any]:
    """
    Remove a custom feed from user's collection

    Args:
        user_ctx: User context with auth and db
        feed_id: ID of the feed to remove

    Returns:
        Success message
    """
    await check_rate_limit(user_ctx, "buzzposter_remove_feed")

    # Find feed
    result = await user_ctx.db.execute(
        select(UserFeed).where(
            UserFeed.id == feed_id,
            UserFeed.user_id == user_ctx.user.id
        )
    )
    feed = result.scalar_one_or_none()

    if not feed:
        return {"error": "Feed not found"}

    # Delete feed
    await user_ctx.db.delete(feed)
    await user_ctx.db.commit()

    await log_usage(user_ctx, "buzzposter_remove_feed")

    return {
        "success": True,
        "message": f"Removed feed: {feed.feed_name}"
    }


async def buzzposter_list_feeds(user_ctx: UserContext) -> Dict[str, Any]:
    """
    List all custom feeds in user's collection

    Args:
        user_ctx: User context with auth and db

    Returns:
        List of user's custom feeds
    """
    await check_rate_limit(user_ctx, "buzzposter_list_feeds")

    # Get all feeds for user
    result = await user_ctx.db.execute(
        select(UserFeed).where(UserFeed.user_id == user_ctx.user.id)
    )
    feeds = result.scalars().all()

    feed_list = []
    for feed in feeds:
        feed_list.append({
            "id": feed.id,
            "name": feed.feed_name,
            "url": feed.feed_url,
            "topic": feed.topic,
            "created_at": feed.created_at.isoformat(),
        })

    await log_usage(user_ctx, "buzzposter_list_feeds")

    return {
        "feeds": feed_list,
        "total": len(feed_list),
    }


async def buzzposter_set_profile(
    user_ctx: UserContext,
    topics: Optional[List[str]] = None,
    location: Optional[str] = None,
    description: Optional[str] = None
) -> Dict[str, Any]:
    """
    Set user's content profile for personalized feed

    Args:
        user_ctx: User context with auth and db
        topics: List of topics of interest
        location: User's location
        description: Description of content preferences

    Returns:
        Updated profile info
    """
    await check_rate_limit(user_ctx, "buzzposter_set_profile")

    # Get or create profile
    result = await user_ctx.db.execute(
        select(UserProfile).where(UserProfile.user_id == user_ctx.user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        profile = UserProfile(user_id=user_ctx.user.id)
        user_ctx.db.add(profile)

    # Update profile fields
    if topics is not None:
        profile.topics = topics
    if location is not None:
        profile.location = location
    if description is not None:
        profile.description = description

    await user_ctx.db.commit()
    await log_usage(user_ctx, "buzzposter_set_profile")

    return {
        "success": True,
        "profile": {
            "topics": profile.topics,
            "location": profile.location,
            "description": profile.description,
        }
    }


async def buzzposter_my_feed(user_ctx: UserContext) -> Dict[str, Any]:
    """
    Get personalized feed based on user's profile and custom feeds

    Args:
        user_ctx: User context with auth and db

    Returns:
        Personalized articles from profile topics and custom feeds
    """
    await check_rate_limit(user_ctx, "buzzposter_my_feed")

    # Get user profile
    result = await user_ctx.db.execute(
        select(UserProfile).where(UserProfile.user_id == user_ctx.user.id)
    )
    profile = result.scalar_one_or_none()

    # Get user's custom feeds
    result = await user_ctx.db.execute(
        select(UserFeed).where(UserFeed.user_id == user_ctx.user.id)
    )
    custom_feeds = result.scalars().all()

    all_articles = []

    # Fetch articles from profile topics
    if profile and profile.topics:
        from .feeds import buzzposter_get_topic
        for topic in profile.topics:
            result = await buzzposter_get_topic(user_ctx, topic)
            if "articles" in result:
                all_articles.extend(result["articles"])

    # Fetch articles from custom feeds
    for feed in custom_feeds:
        result = await buzzposter_get_feed(user_ctx, feed.feed_url)
        if "articles" in result:
            for article in result["articles"]:
                article["source"] = feed.feed_name
            all_articles.extend(result["articles"])

    # Sort by published date
    all_articles.sort(
        key=lambda x: x.get("published", ""),
        reverse=True
    )

    await log_usage(user_ctx, "buzzposter_my_feed")

    return {
        "articles": all_articles[:50],  # Top 50 articles
        "total": len(all_articles),
        "profile_topics": profile.topics if profile else [],
        "custom_feeds": len(custom_feeds),
    }
