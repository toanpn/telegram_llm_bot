from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    """User model for storing user information."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(50), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    stored_info = relationship("UserInfo", back_populates="user")

class UserInfo(Base):
    """Model for storing user information as key-value pairs."""
    __tablename__ = "user_info"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    key = Column(String(100), nullable=False)
    value = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="stored_info")

class GroupSettings(Base):
    """Model for storing group-specific bot settings."""
    __tablename__ = "group_settings"
    
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, unique=True, nullable=False)
    group_title = Column(String(200), nullable=True)
    
    # AI Settings
    gemini_model = Column(String(50), default="gemini-pro")
    temperature = Column(Float, default=0.7)
    tone = Column(String(50), default="friendly")
    
    # Bot Behavior Settings
    context_messages_count = Column(Integer, default=7)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ConversationLog(Base):
    """Model for storing conversation logs for context and analysis."""
    __tablename__ = "conversation_logs"
    
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=False)
    message_id = Column(Integer, nullable=False)
    message_text = Column(Text, nullable=True)
    message_type = Column(String(20), default="text")  # text, photo, document, etc.
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # For context tracking
    is_bot_message = Column(Boolean, default=False)
    is_reply = Column(Boolean, default=False)
    reply_to_message_id = Column(Integer, nullable=True) 