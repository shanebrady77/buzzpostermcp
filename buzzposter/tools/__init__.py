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
from .media import (
    buzzposter_upload_media,
    buzzposter_list_media,
    buzzposter_delete_media,
    buzzposter_get_storage_usage,
    buzzposter_post_with_media,
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
    # Media tools
    "buzzposter_upload_media",
    "buzzposter_list_media",
    "buzzposter_delete_media",
    "buzzposter_get_storage_usage",
    "buzzposter_post_with_media",
]
