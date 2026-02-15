"""
Authentication module for BuzzPoster
"""
from .middleware import (
    UserContext,
    validate_api_key,
    check_rate_limit,
    check_feature_access,
    log_usage,
    get_user_from_request,
)
from .late_oauth import (
    generate_oauth_state,
    resolve_oauth_state,
    get_authorization_url,
    exchange_code_for_token,
    refresh_access_token,
    save_tokens,
    clear_tokens,
    validate_token,
    check_connection_status,
)
from .stripe import (
    create_checkout_session,
    handle_checkout_completed,
    verify_webhook_signature,
)

__all__ = [
    "UserContext",
    "validate_api_key",
    "check_rate_limit",
    "check_feature_access",
    "log_usage",
    "get_user_from_request",
    "generate_oauth_state",
    "resolve_oauth_state",
    "get_authorization_url",
    "exchange_code_for_token",
    "refresh_access_token",
    "save_tokens",
    "clear_tokens",
    "validate_token",
    "check_connection_status",
    "create_checkout_session",
    "handle_checkout_completed",
    "verify_webhook_signature",
]
