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
    buzzposter_late_connection,
)
from .media import (
    buzzposter_upload_media,
    buzzposter_list_media,
    buzzposter_delete_media,
    buzzposter_get_storage_usage,
    buzzposter_post_with_media,
)
from .integrations import (
    buzzposter_draft_beehiiv,
    buzzposter_publish_beehiiv,
    buzzposter_draft_kit,
    buzzposter_publish_kit,
    buzzposter_draft_mailchimp,
    buzzposter_publish_mailchimp,
    buzzposter_draft_wordpress,
    buzzposter_publish_wordpress,
    buzzposter_draft_ghost,
    buzzposter_publish_ghost,
    buzzposter_draft_webflow,
    buzzposter_publish_webflow,
    buzzposter_connect_platform,
    buzzposter_list_integrations,
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
    "buzzposter_late_connection",
    # Media tools
    "buzzposter_upload_media",
    "buzzposter_list_media",
    "buzzposter_delete_media",
    "buzzposter_get_storage_usage",
    "buzzposter_post_with_media",
    # Integration tools
    "buzzposter_draft_beehiiv",
    "buzzposter_publish_beehiiv",
    "buzzposter_draft_kit",
    "buzzposter_publish_kit",
    "buzzposter_draft_mailchimp",
    "buzzposter_publish_mailchimp",
    "buzzposter_draft_wordpress",
    "buzzposter_publish_wordpress",
    "buzzposter_draft_ghost",
    "buzzposter_publish_ghost",
    "buzzposter_draft_webflow",
    "buzzposter_publish_webflow",
    "buzzposter_connect_platform",
    "buzzposter_list_integrations",
]
