"""
RSS and NewsAPI content sourcing tools
"""
import os
import re
import httpx
import feedparser
from datetime import datetime
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from ..auth.middleware import UserContext, check_rate_limit, check_feature_access, log_usage


NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
NEWSAPI_BASE_URL = "https://newsapi.org/v2"


# Built-in RSS feeds by topic
BUILT_IN_FEEDS = {
    "tech": [
        {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
        {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml"},
        {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index"},
    ],
    "business": [
        {"name": "Wall Street Journal", "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml"},
        {"name": "Bloomberg", "url": "https://www.bloomberg.com/feed/podcast/business-of-sports.xml"},
        {"name": "Forbes", "url": "https://www.forbes.com/real-time/feed2/"},
    ],
    "science": [
        {"name": "Scientific American", "url": "https://www.scientificamerican.com/feed/"},
        {"name": "Nature", "url": "https://www.nature.com/nature.rss"},
        {"name": "Science Daily", "url": "https://www.sciencedaily.com/rss/all.xml"},
    ],
}


def extract_image_from_entry(entry: Any) -> Optional[str]:
    """
    Extract first available image URL from RSS feed entry.
    Checks in priority order:
    1. media:content or media:thumbnail (common in modern feeds)
    2. enclosure tags with image MIME types
    3. First <img> tag in HTML content

    Args:
        entry: feedparser entry object

    Returns:
        Image URL string or None if no image found
    """
    # Check media:content (common in feeds with embedded media)
    if hasattr(entry, 'media_content') and entry.media_content:
        for media in entry.media_content:
            if media.get('medium') == 'image' or media.get('type', '').startswith('image/'):
                url = media.get('url')
                if url:
                    return url

    # Check media:thumbnail
    if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        url = entry.media_thumbnail[0].get('url')
        if url:
            return url

    # Check enclosures for images
    if hasattr(entry, 'enclosures'):
        for enclosure in entry.enclosures:
            if enclosure.get('type', '').startswith('image/'):
                url = enclosure.get('href') or enclosure.get('url')
                if url:
                    return url

    # Parse HTML content for <img> tags
    html_content = entry.get('content', [{}])[0].get('value') if entry.get('content') else None
    if not html_content:
        html_content = entry.get('summary') or entry.get('description')

    if html_content:
        try:
            soup = BeautifulSoup(html_content, 'html5lib')
            img = soup.find('img')
            if img and img.get('src'):
                src = img.get('src')
                # Validate it's a reasonable URL
                if src and (src.startswith('http://') or src.startswith('https://')):
                    return src
        except Exception:
            # Silently fail on HTML parsing errors
            pass

    return None


async def buzzposter_get_feed(user_ctx: UserContext, feed_url: str) -> Dict[str, Any]:
    """
    Fetch and parse any RSS feed

    Args:
        user_ctx: User context with auth and db
        feed_url: URL of the RSS feed to fetch

    Returns:
        Dict with feed metadata and articles
    """
    await check_rate_limit(user_ctx, "buzzposter_get_feed")

    try:
        # Fetch feed
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(feed_url)
            response.raise_for_status()

        # Parse feed
        feed = feedparser.parse(response.text)

        # Extract articles
        articles = []
        for entry in feed.entries[:20]:  # Limit to 20 most recent
            articles.append({
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "description": entry.get("summary", entry.get("description", "")),
                "published": entry.get("published", entry.get("updated", "")),
                "author": entry.get("author", ""),
                "image_url": extract_image_from_entry(entry),
            })

        await log_usage(user_ctx, "buzzposter_get_feed")

        return {
            "feed_title": feed.feed.get("title", ""),
            "feed_description": feed.feed.get("description", ""),
            "articles": articles,
            "total": len(articles),
        }

    except httpx.HTTPError as e:
        return {"error": f"Failed to fetch feed: {str(e)}"}
    except Exception as e:
        return {"error": f"Failed to parse feed: {str(e)}"}


async def buzzposter_get_topic(user_ctx: UserContext, topic: str) -> Dict[str, Any]:
    """
    Get news articles from built-in topic feeds

    Args:
        user_ctx: User context with auth and db
        topic: Topic category (tech, business, science)

    Returns:
        Dict with articles from all feeds in that topic
    """
    await check_rate_limit(user_ctx, "buzzposter_get_topic")

    # Free tier only gets built-in topics
    if user_ctx.tier == "free" and topic not in BUILT_IN_FEEDS:
        await check_feature_access(user_ctx, "unlimited_topics")

    # Get feeds for topic
    feeds = BUILT_IN_FEEDS.get(topic.lower())
    if not feeds:
        return {"error": f"Unknown topic: {topic}. Available: {', '.join(BUILT_IN_FEEDS.keys())}"}

    # Fetch all feeds for this topic
    all_articles = []
    for feed_info in feeds:
        result = await buzzposter_get_feed(user_ctx, feed_info["url"])
        if "articles" in result:
            for article in result["articles"]:
                article["source"] = feed_info["name"]
            all_articles.extend(result["articles"])

    # Sort by published date (most recent first)
    all_articles.sort(
        key=lambda x: x.get("published", ""),
        reverse=True
    )

    await log_usage(user_ctx, "buzzposter_get_topic")

    return {
        "topic": topic,
        "articles": all_articles[:30],  # Return top 30
        "total": len(all_articles),
    }


async def buzzposter_search_news(
    user_ctx: UserContext,
    query: str,
    language: str = "en",
    sort_by: str = "publishedAt"
) -> Dict[str, Any]:
    """
    Search news articles using NewsAPI
    Requires Pro or Business tier

    Args:
        user_ctx: User context with auth and db
        query: Search keywords
        language: Language code (default: en)
        sort_by: Sort order (publishedAt, relevancy, popularity)

    Returns:
        Dict with search results
    """
    await check_rate_limit(user_ctx, "buzzposter_search_news")
    await check_feature_access(user_ctx, "newsapi_search")

    if not NEWSAPI_KEY:
        return {"error": "NewsAPI key not configured on server"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{NEWSAPI_BASE_URL}/everything",
                params={
                    "q": query,
                    "language": language,
                    "sortBy": sort_by,
                    "pageSize": 20,
                    "apiKey": NEWSAPI_KEY,
                }
            )
            response.raise_for_status()
            data = response.json()

        # Transform to consistent format
        articles = []
        for article in data.get("articles", []):
            articles.append({
                "title": article.get("title", ""),
                "link": article.get("url", ""),
                "description": article.get("description", ""),
                "published": article.get("publishedAt", ""),
                "author": article.get("author", ""),
                "source": article.get("source", {}).get("name", ""),
                "image_url": article.get("urlToImage", ""),
            })

        await log_usage(user_ctx, "buzzposter_search_news")

        return {
            "query": query,
            "articles": articles,
            "total": data.get("totalResults", 0),
        }

    except httpx.HTTPError as e:
        return {"error": f"NewsAPI request failed: {str(e)}"}
    except Exception as e:
        return {"error": f"Failed to search news: {str(e)}"}
