"""
Cloudflare R2 media upload and management tools
"""
import os
import io
import base64
import hashlib
import mimetypes
from typing import Dict, Any, Optional, List
from datetime import datetime
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from sqlalchemy import select, func

from ..auth.middleware import UserContext, check_rate_limit, check_feature_access, log_usage
from ..db.models import Media


# R2 Configuration
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "")

# Tier storage limits
TIER_STORAGE_LIMITS = {
    "free": {"max_storage_bytes": 0, "max_file_bytes": 0},
    "pro": {"max_storage_bytes": 1_073_741_824, "max_file_bytes": 10_485_760},      # 1GB, 10MB
    "business": {"max_storage_bytes": 10_737_418_240, "max_file_bytes": 104_857_600}  # 10GB, 100MB
}

# Allowed MIME types
ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/gif",
    "image/webp", "image/svg+xml", "video/mp4", "video/webm"
}


def _get_r2_client():
    """Initialize and return boto3 S3 client configured for Cloudflare R2"""
    if not all([R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME]):
        raise ValueError("R2 configuration incomplete. Check environment variables.")

    endpoint_url = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

    s3_client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
    )
    return s3_client


async def _validate_file_access(user_ctx: UserContext, file_size: int) -> Dict[str, Any]:
    """
    Validate user has access to upload files and check quotas

    Args:
        user_ctx: User context
        file_size: Size of file to upload in bytes

    Returns:
        Dict with validation result or error
    """
    # Check feature access (Pro/Business only)
    await check_feature_access(user_ctx, "media_upload")

    # Get tier limits
    limits = TIER_STORAGE_LIMITS.get(user_ctx.tier, TIER_STORAGE_LIMITS["free"])

    # Check file size limit
    if file_size > limits["max_file_bytes"]:
        return {
            "error": f"File too large for {user_ctx.tier} tier. Max: {limits['max_file_bytes'] / 1_048_576:.1f}MB"
        }

    # Check total storage usage
    stmt = select(func.sum(Media.size_bytes)).where(Media.user_id == user_ctx.user.id)
    result = await user_ctx.db.execute(stmt)
    total_usage = result.scalar() or 0

    if total_usage + file_size > limits["max_storage_bytes"]:
        return {
            "error": f"Storage limit reached. Used: {total_usage / 1_048_576:.1f}MB, Limit: {limits['max_storage_bytes'] / 1_048_576:.1f}MB. Delete files or upgrade tier."
        }

    return {"valid": True}


async def buzzposter_upload_media(
    user_ctx: UserContext,
    file_data: str,
    filename: str,
    content_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Upload media file to R2 storage. Returns public URL.
    Pro/Business only.

    Args:
        user_ctx: User context with auth and db
        file_data: Base64-encoded file data
        filename: Original filename with extension
        content_type: MIME type (optional, auto-detected if not provided)

    Returns:
        Dict with URL or error
    """
    await check_rate_limit(user_ctx, "buzzposter_upload_media")

    try:
        # Decode base64 data
        try:
            file_bytes = base64.b64decode(file_data)
        except Exception as e:
            return {"error": f"Invalid base64 data: {str(e)}"}

        file_size = len(file_bytes)

        # Validate access and quotas
        validation = await _validate_file_access(user_ctx, file_size)
        if "error" in validation:
            return validation

        # Determine content type
        if not content_type:
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                content_type = "application/octet-stream"

        # Validate MIME type
        if content_type not in ALLOWED_MIME_TYPES:
            return {
                "error": f"File type not supported: {content_type}. Allowed types: {', '.join(ALLOWED_MIME_TYPES)}"
            }

        # Generate unique R2 key
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        file_hash = hashlib.md5(file_bytes).hexdigest()[:8]
        r2_key = f"{user_ctx.user.id}/{timestamp}_{file_hash}_{filename}"

        # Upload to R2
        s3_client = _get_r2_client()
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                s3_client.put_object(
                    Bucket=R2_BUCKET_NAME,
                    Key=r2_key,
                    Body=file_bytes,
                    ContentType=content_type
                )
                break  # Success
            except ClientError as e:
                last_error = e
                if attempt == max_retries - 1:
                    return {"error": f"R2 upload failed after {max_retries} attempts: {str(e)}"}

        # Generate public URL
        public_url = f"{R2_PUBLIC_URL.rstrip('/')}/{r2_key}" if R2_PUBLIC_URL else f"https://{R2_BUCKET_NAME}.r2.dev/{r2_key}"

        # Save metadata to database
        media = Media(
            user_id=user_ctx.user.id,
            filename=filename,
            r2_key=r2_key,
            url=public_url,
            content_type=content_type,
            size_bytes=file_size
        )
        user_ctx.db.add(media)
        await user_ctx.db.commit()
        await user_ctx.db.refresh(media)

        await log_usage(user_ctx, "buzzposter_upload_media")

        return {
            "success": True,
            "media_id": media.id,
            "url": public_url,
            "filename": filename,
            "size_bytes": file_size,
            "content_type": content_type
        }

    except Exception as e:
        # Attempt cleanup if database save failed but R2 upload succeeded
        try:
            if 'r2_key' in locals():
                s3_client = _get_r2_client()
                s3_client.delete_object(Bucket=R2_BUCKET_NAME, Key=r2_key)
        except:
            pass  # Cleanup failed, log it but don't mask original error

        return {"error": f"Upload failed: {str(e)}"}


async def buzzposter_list_media(user_ctx: UserContext) -> Dict[str, Any]:
    """
    List all media files uploaded by the user

    Args:
        user_ctx: User context with auth and db

    Returns:
        Dict with media list
    """
    await check_rate_limit(user_ctx, "buzzposter_list_media")

    try:
        # Query user's media
        stmt = select(Media).where(Media.user_id == user_ctx.user.id).order_by(Media.created_at.desc())
        result = await user_ctx.db.execute(stmt)
        media_files = result.scalars().all()

        # Calculate total usage
        total_usage = sum(m.size_bytes for m in media_files)
        tier_limit = TIER_STORAGE_LIMITS.get(user_ctx.tier, TIER_STORAGE_LIMITS["free"])["max_storage_bytes"]

        await log_usage(user_ctx, "buzzposter_list_media")

        return {
            "media_files": [
                {
                    "id": m.id,
                    "filename": m.filename,
                    "url": m.url,
                    "content_type": m.content_type,
                    "size_bytes": m.size_bytes,
                    "created_at": m.created_at.isoformat()
                }
                for m in media_files
            ],
            "total_files": len(media_files),
            "total_usage_bytes": total_usage,
            "tier_limit_bytes": tier_limit,
            "usage_percentage": (total_usage / tier_limit * 100) if tier_limit > 0 else 0
        }

    except Exception as e:
        return {"error": f"Failed to list media: {str(e)}"}


async def buzzposter_delete_media(user_ctx: UserContext, media_id: int) -> Dict[str, Any]:
    """
    Delete a media file

    Args:
        user_ctx: User context with auth and db
        media_id: ID of media file to delete

    Returns:
        Dict with success status or error
    """
    await check_rate_limit(user_ctx, "buzzposter_delete_media")

    try:
        # Find media and verify ownership
        stmt = select(Media).where(Media.id == media_id, Media.user_id == user_ctx.user.id)
        result = await user_ctx.db.execute(stmt)
        media = result.scalar_one_or_none()

        if not media:
            return {"error": "Media file not found or access denied"}

        # Delete from R2
        try:
            s3_client = _get_r2_client()
            s3_client.delete_object(Bucket=R2_BUCKET_NAME, Key=media.r2_key)
        except ClientError as e:
            # Continue even if R2 deletion fails (orphaned file)
            pass

        # Delete from database
        await user_ctx.db.delete(media)
        await user_ctx.db.commit()

        await log_usage(user_ctx, "buzzposter_delete_media")

        return {
            "success": True,
            "message": f"Deleted {media.filename}",
            "media_id": media_id
        }

    except Exception as e:
        return {"error": f"Failed to delete media: {str(e)}"}


async def buzzposter_get_storage_usage(user_ctx: UserContext) -> Dict[str, Any]:
    """
    Get storage usage information for the user

    Args:
        user_ctx: User context with auth and db

    Returns:
        Dict with storage usage stats
    """
    await check_rate_limit(user_ctx, "buzzposter_get_storage_usage")

    try:
        # Query total usage
        stmt = select(
            func.count(Media.id),
            func.sum(Media.size_bytes)
        ).where(Media.user_id == user_ctx.user.id)
        result = await user_ctx.db.execute(stmt)
        count, total_bytes = result.one()

        total_bytes = total_bytes or 0
        tier_limits = TIER_STORAGE_LIMITS.get(user_ctx.tier, TIER_STORAGE_LIMITS["free"])

        await log_usage(user_ctx, "buzzposter_get_storage_usage")

        return {
            "tier": user_ctx.tier,
            "total_files": count,
            "used_bytes": total_bytes,
            "used_mb": round(total_bytes / 1_048_576, 2),
            "limit_bytes": tier_limits["max_storage_bytes"],
            "limit_mb": round(tier_limits["max_storage_bytes"] / 1_048_576, 2),
            "max_file_bytes": tier_limits["max_file_bytes"],
            "max_file_mb": round(tier_limits["max_file_bytes"] / 1_048_576, 2),
            "usage_percentage": round((total_bytes / tier_limits["max_storage_bytes"] * 100), 2) if tier_limits["max_storage_bytes"] > 0 else 0
        }

    except Exception as e:
        return {"error": f"Failed to get storage usage: {str(e)}"}


async def buzzposter_post_with_media(
    user_ctx: UserContext,
    platform: str,
    content: str,
    media_data: Optional[str] = None,
    media_filename: Optional[str] = None,
    account_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convenience tool: Upload media and post to social media in one call.
    Pro/Business only.

    Args:
        user_ctx: User context with auth and db
        platform: Social platform (twitter, linkedin, etc)
        content: Post content text
        media_data: Optional base64-encoded media file
        media_filename: Optional filename for media
        account_id: Optional specific account ID

    Returns:
        Dict with post result
    """
    await check_rate_limit(user_ctx, "buzzposter_post_with_media")

    try:
        media_url = None

        # Upload media if provided
        if media_data and media_filename:
            upload_result = await buzzposter_upload_media(user_ctx, media_data, media_filename)
            if "error" in upload_result:
                return upload_result
            media_url = upload_result["url"]

        # Import here to avoid circular dependency
        from .social import buzzposter_post

        # Post to social media
        post_args = {
            "platform": platform,
            "content": content
        }
        if media_url:
            post_args["media_urls"] = [media_url]
        if account_id:
            post_args["account_id"] = account_id

        post_result = await buzzposter_post(user_ctx, **post_args)

        await log_usage(user_ctx, "buzzposter_post_with_media")

        return {
            "success": True,
            "post": post_result,
            "media_url": media_url
        }

    except Exception as e:
        return {"error": f"Failed to post with media: {str(e)}"}
