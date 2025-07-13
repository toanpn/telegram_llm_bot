import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy import create_engine, select, and_, or_, desc, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger

from config import config
from models import Base, User, UserInfo, GroupSettings, ConversationLog

class DatabaseService:
    """Service for handling database operations."""
    
    def __init__(self):
        self.engine = None
        self.async_session = None
        self.sync_session = None
    
    async def initialize(self):
        """Initialize the database connection and create tables."""
        try:
            # Create async engine for async operations
            if config.database_url.startswith("sqlite"):
                # Convert sqlite URL to async version
                async_url = config.database_url.replace("sqlite://", "sqlite+aiosqlite://")
                self.engine = create_async_engine(async_url, echo=config.debug)
            else:
                self.engine = create_async_engine(config.database_url, echo=config.debug)
            
            # Create async session factory
            self.async_session = async_sessionmaker(self.engine, expire_on_commit=False)
            
            # Create tables
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            logger.info("Database service initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    async def get_or_create_user(self, telegram_id: int, username: str = None, 
                               first_name: str = None, last_name: str = None) -> User:
        """Get existing user or create new one."""
        async with self.async_session() as session:
            # Try to find existing user
            stmt = select(User).where(User.telegram_id == telegram_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if user:
                # Update user info if provided
                if username and user.username != username:
                    user.username = username
                if first_name and user.first_name != first_name:
                    user.first_name = first_name
                if last_name and user.last_name != last_name:
                    user.last_name = last_name
                
                user.updated_at = datetime.utcnow()
                await session.commit()
                return user
            else:
                # Create new user
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                return user
    
    async def save_user_info(self, user_id: int, key: str, value: str) -> bool:
        """Save user information as key-value pair."""
        try:
            async with self.async_session() as session:
                # Get user by telegram_id
                stmt = select(User).where(User.telegram_id == user_id)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                
                if not user:
                    # Create user if doesn't exist
                    user = await self.get_or_create_user(user_id)
                
                # Check if info already exists
                info_stmt = select(UserInfo).where(
                    and_(UserInfo.user_id == user.id, UserInfo.key == key)
                )
                info_result = await session.execute(info_stmt)
                existing_info = info_result.scalar_one_or_none()
                
                if existing_info:
                    # Update existing info
                    existing_info.value = value
                    existing_info.updated_at = datetime.utcnow()
                else:
                    # Create new info
                    user_info = UserInfo(
                        user_id=user.id,
                        key=key,
                        value=value
                    )
                    session.add(user_info)
                
                await session.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error saving user info: {e}")
            return False
    
    async def get_user_info(self, user_id: int, key: str) -> Optional[UserInfo]:
        """Get user information by key."""
        try:
            async with self.async_session() as session:
                # Get user by telegram_id
                user_stmt = select(User).where(User.telegram_id == user_id)
                user_result = await session.execute(user_stmt)
                user = user_result.scalar_one_or_none()
                
                if not user:
                    return None
                
                # Get user info
                info_stmt = select(UserInfo).where(
                    and_(UserInfo.user_id == user.id, UserInfo.key == key)
                )
                info_result = await session.execute(info_stmt)
                return info_result.scalar_one_or_none()
                
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return None
    
    async def get_user_info_by_username(self, username: str, key: str) -> Optional[UserInfo]:
        """Get user information by username and key."""
        try:
            async with self.async_session() as session:
                # Get user by username
                user_stmt = select(User).where(User.username == username)
                user_result = await session.execute(user_stmt)
                user = user_result.scalar_one_or_none()
                
                if not user:
                    return None
                
                # Get user info
                info_stmt = select(UserInfo).where(
                    and_(UserInfo.user_id == user.id, UserInfo.key == key)
                )
                info_result = await session.execute(info_stmt)
                return info_result.scalar_one_or_none()
                
        except Exception as e:
            logger.error(f"Error getting user info by username: {e}")
            return None
    
    async def get_group_settings(self, group_id: int) -> GroupSettings:
        """Get group settings or create default ones."""
        async with self.async_session() as session:
            # Try to find existing settings
            stmt = select(GroupSettings).where(GroupSettings.group_id == group_id)
            result = await session.execute(stmt)
            settings = result.scalar_one_or_none()
            
            if not settings:
                # Create default settings
                settings = GroupSettings(
                    group_id=group_id,
                    gemini_model=config.gemini_model,
                    temperature=config.default_temperature,
                    tone=config.default_tone,
                    context_messages_count=config.context_messages_count
                )
                session.add(settings)
                await session.commit()
                await session.refresh(settings)
            
            return settings
    
    async def update_group_settings(self, group_id: int, **kwargs) -> bool:
        """Update group settings."""
        try:
            async with self.async_session() as session:
                # Get or create settings
                settings = await self.get_group_settings(group_id)
                
                # Update settings
                for key, value in kwargs.items():
                    if hasattr(settings, key):
                        setattr(settings, key, value)
                
                settings.updated_at = datetime.utcnow()
                
                # Merge changes
                session.add(settings)
                await session.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error updating group settings: {e}")
            return False
    
    async def log_conversation(self, group_id: int, user_id: int, message_id: int,
                             message_text: str, message_type: str = "text",
                             is_bot_message: bool = False, is_reply: bool = False,
                             reply_to_message_id: int = None) -> bool:
        """Log a conversation message."""
        try:
            async with self.async_session() as session:
                log_entry = ConversationLog(
                    group_id=group_id,
                    user_id=user_id,
                    message_id=message_id,
                    message_text=message_text,
                    message_type=message_type,
                    is_bot_message=is_bot_message,
                    is_reply=is_reply,
                    reply_to_message_id=reply_to_message_id
                )
                session.add(log_entry)
                await session.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error logging conversation: {e}")
            return False
    
    async def get_recent_messages(self, group_id: int, limit: int = 10) -> List[Dict]:
        """Get recent messages from a group."""
        try:
            async with self.async_session() as session:
                # Get recent messages with user info
                stmt = (
                    select(ConversationLog, User)
                    .join(User, ConversationLog.user_id == User.telegram_id)
                    .where(ConversationLog.group_id == group_id)
                    .order_by(desc(ConversationLog.timestamp))
                    .limit(limit)
                )
                
                result = await session.execute(stmt)
                rows = result.fetchall()
                
                messages = []
                for log, user in rows:
                    messages.append({
                        'message_id': log.message_id,
                        'user_id': log.user_id,
                        'username': user.username or user.first_name or 'Unknown',
                        'message_text': log.message_text,
                        'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                        'is_bot_message': log.is_bot_message,
                        'is_reply': log.is_reply
                    })
                
                # Return in chronological order (oldest first)
                return list(reversed(messages))
                
        except Exception as e:
            logger.error(f"Error getting recent messages: {e}")
            return []
    
    async def get_conversation_history(self, group_id: int, hours: int = 24) -> List[Dict]:
        """Get conversation history for a specific time period."""
        try:
            async with self.async_session() as session:
                # Calculate time threshold
                time_threshold = datetime.utcnow() - timedelta(hours=hours)
                
                # Get messages with user info
                stmt = (
                    select(ConversationLog, User)
                    .join(User, ConversationLog.user_id == User.telegram_id)
                    .where(
                        and_(
                            ConversationLog.group_id == group_id,
                            ConversationLog.timestamp >= time_threshold
                        )
                    )
                    .order_by(ConversationLog.timestamp)
                )
                
                result = await session.execute(stmt)
                rows = result.fetchall()
                
                messages = []
                for log, user in rows:
                    messages.append({
                        'message_id': log.message_id,
                        'user_id': log.user_id,
                        'username': user.username or user.first_name or 'Unknown',
                        'message_text': log.message_text,
                        'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                        'is_bot_message': log.is_bot_message,
                        'is_reply': log.is_reply
                    })
                
                return messages
                
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []
    
    async def cleanup_old_logs(self, days: int = 30) -> bool:
        """Clean up old conversation logs."""
        try:
            async with self.async_session() as session:
                # Calculate time threshold
                time_threshold = datetime.utcnow() - timedelta(days=days)
                
                # Delete old logs
                stmt = select(ConversationLog).where(
                    ConversationLog.timestamp < time_threshold
                )
                result = await session.execute(stmt)
                old_logs = result.scalars().all()
                
                for log in old_logs:
                    await session.delete(log)
                
                await session.commit()
                
                logger.info(f"Cleaned up {len(old_logs)} old conversation logs")
                return True
                
        except Exception as e:
            logger.error(f"Error cleaning up old logs: {e}")
            return False
    
    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Get user statistics."""
        try:
            async with self.async_session() as session:
                # Get user
                user_stmt = select(User).where(User.telegram_id == user_id)
                user_result = await session.execute(user_stmt)
                user = user_result.scalar_one_or_none()
                
                if not user:
                    return {}
                
                # Get message count
                message_count_stmt = select(func.count(ConversationLog.id)).where(
                    ConversationLog.user_id == user_id
                )
                message_count_result = await session.execute(message_count_stmt)
                message_count = message_count_result.scalar()
                
                # Get stored info count
                info_count_stmt = select(func.count(UserInfo.id)).where(
                    UserInfo.user_id == user.id
                )
                info_count_result = await session.execute(info_count_stmt)
                info_count = info_count_result.scalar()
                
                return {
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'created_at': user.created_at,
                    'message_count': message_count,
                    'stored_info_count': info_count
                }
                
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return {} 