"""
Database models for BuzzPoster MCP Server
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, JSON, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    buzzposter_api_key = Column(String(255), unique=True, nullable=False, index=True)
    tier = Column(String(50), default="free", nullable=False)  # free, pro, business
    late_oauth_token = Column(Text, nullable=True)
    late_refresh_token = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    usage_logs = relationship("UsageLog", back_populates="user", cascade="all, delete-orphan")
    user_feeds = relationship("UserFeed", back_populates="user", cascade="all, delete-orphan")
    user_profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    media_files = relationship("Media", back_populates="user", cascade="all, delete-orphan")
    integrations = relationship("UserIntegration", back_populates="user", cascade="all, delete-orphan")
    connected_stores = relationship("ConnectedStore", back_populates="user", cascade="all, delete-orphan")


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tool_name = Column(String(255), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationship
    user = relationship("User", back_populates="usage_logs")

    # Index for efficient daily usage queries
    __table_args__ = (
        Index('idx_user_timestamp', 'user_id', 'timestamp'),
    )


class UserFeed(Base):
    __tablename__ = "user_feeds"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    feed_url = Column(Text, nullable=False)
    feed_name = Column(String(255), nullable=False)
    topic = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship
    user = relationship("User", back_populates="user_feeds")

    # Index for efficient user feed queries
    __table_args__ = (
        Index('idx_user_feeds', 'user_id'),
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    topics = Column(JSON, nullable=True)  # JSON array of topics
    location = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)

    # Relationship
    user = relationship("User", back_populates="user_profile")


class Media(Base):
    __tablename__ = "media"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    r2_key = Column(String(512), nullable=False, unique=True)  # Storage path in R2
    url = Column(Text, nullable=False)  # Public URL
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship
    user = relationship("User", back_populates="media_files")

    # Indexes for efficient queries
    __table_args__ = (
        Index('idx_user_media', 'user_id'),
        Index('idx_r2_key', 'r2_key'),
    )


class UserIntegration(Base):
    __tablename__ = "user_integrations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    platform = Column(String(50), nullable=False)  # beehiiv, kit, mailchimp, wordpress, ghost, webflow
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    metadata = Column(JSON, nullable=True)  # Platform-specific data (pub_id, list_id, site_url, etc.)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationship
    user = relationship("User", back_populates="integrations")

    # Indexes for efficient queries
    __table_args__ = (
        Index('idx_user_platform', 'user_id', 'platform'),
    )


class ConnectedStore(Base):
    __tablename__ = "connected_stores"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    platform = Column(String(50), nullable=False)  # shopify, woocommerce, etsy
    store_domain = Column(String(255), nullable=True)  # Shopify/WooCommerce store domain
    shop_id = Column(String(255), nullable=True)  # Etsy shop ID
    credentials = Column(JSON, nullable=False)  # Platform-specific credentials (encrypted storage recommended)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationship
    user = relationship("User", back_populates="connected_stores")

    # Indexes for efficient queries
    __table_args__ = (
        Index('idx_user_store', 'user_id', 'platform'),
    )
