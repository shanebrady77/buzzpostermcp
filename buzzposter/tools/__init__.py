"""
MCP Tools for BuzzPoster
"""
from .feeds import (
    buzzposter_get_feed,
    buzzposter_get_topic,
    buzzposter_search_news,
)
from .profile import (
    buzzposter_add_feed,
    buzzposter_remove_feed,
    buzzposter_list_feeds,
    buzzposter_set_profile,
    buzzposter_my_feed,
)
from .social import (
    buzzposter_list_social_accounts,
    buzzposter_post,
    buzzposter_cross_post,
    buzzposter_schedule_post,
    buzzposter_list_posts,
    buzzposter_post_analytics,
)

__all__ = [
    # Feed tools
    "buzzposter_get_feed",
    "buzzposter_get_topic",
    "buzzposter_search_news",
    # Profile tools
    "buzzposter_add_feed",
    "buzzposter_remove_feed",
    "buzzposter_list_feeds",
    "buzzposter_set_profile",
    "buzzposter_my_feed",
    # Social tools
    "buzzposter_list_social_accounts",
    "buzzposter_post",
    "buzzposter_cross_post",
    "buzzposter_schedule_post",
    "buzzposter_list_posts",
    "buzzposter_post_analytics",
]
