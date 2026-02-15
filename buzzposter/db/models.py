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
