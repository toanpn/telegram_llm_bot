import asyncio
import logging
import signal
from datetime import datetime
from typing import List, Optional, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Chat
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatType

from sqlalchemy import create_engine, select, and_
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import google.generativeai as genai
from loguru import logger

from config import config, validate_config
from models import Base, User, UserInfo, GroupSettings, ConversationLog
from gemini_service import GeminiService
from database_service import DatabaseService

class TelegramBot:
    """Main Telegram bot class."""
    
    def __init__(self):
        self.application = None
        self.db_service = None
        self.gemini_service = None
        
    async def initialize(self):
        """Initialize the bot with all services."""
        # Validate configuration
        validate_config()
        
        # Initialize services
        self.db_service = DatabaseService()
        await self.db_service.initialize()
        
        self.gemini_service = GeminiService()
        
        # Create Telegram application
        self.application = Application.builder().token(config.telegram_bot_token).build()
        
        # Verify bot information
        await self._verify_bot_info()
        
        # Add handlers
        self._add_handlers()
        
        logger.info("Bot initialized successfully")
    
    async def _verify_bot_info(self):
        """Verify bot information and log for debugging."""
        try:
            # Get bot info from Telegram
            bot_info = await self.application.bot.get_me()
            
            logger.info(f"Bot info from Telegram:")
            logger.info(f"  - ID: {bot_info.id}")
            logger.info(f"  - Username: @{bot_info.username}")
            logger.info(f"  - First Name: {bot_info.first_name}")
            logger.info(f"  - Last Name: {bot_info.last_name}")
            
            logger.info(f"Bot info from config:")
            logger.info(f"  - Configured username: {config.bot_username}")
            
            # Warn if usernames don't match
            if config.bot_username != bot_info.username:
                logger.warning(f"Configuration mismatch! Config has '{config.bot_username}' but bot's actual username is '{bot_info.username}'")
                logger.warning("This may cause issues with mention detection in groups")
                
        except Exception as e:
            logger.error(f"Error verifying bot info: {e}")
            raise
    
    def _add_handlers(self):
        """Add message and command handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("settings", self.settings_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("test", self.test_command))
        
        # Message handlers
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_message
        ))
        
        # Callback query handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        
        logger.info("Handlers added successfully")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages."""
        if not update.message or not update.message.text:
            return
        
        # Log basic message info
        logger.info(f"Received message in {update.effective_chat.type} chat: '{update.message.text[:50]}...'")
        
        # Check if this is a group chat
        if update.effective_chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            await self._handle_group_message(update, context)
        else:
            await self._handle_private_message(update, context)
    
    async def _handle_group_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle messages in group chats."""
        message = update.message
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        logger.debug(f"Processing group message from user {user_id} in chat {chat_id}")
        
        try:
            # Ensure user exists in database
            await self.db_service.get_or_create_user(
                telegram_id=user_id,
                username=update.effective_user.username,
                first_name=update.effective_user.first_name,
                last_name=update.effective_user.last_name
            )
            
            # Store message in conversation log
            await self.db_service.log_conversation(
                group_id=chat_id,
                user_id=user_id,
                message_id=message.message_id,
                message_text=message.text,
                is_bot_message=False,
                is_reply=message.reply_to_message is not None,
                reply_to_message_id=message.reply_to_message.message_id if message.reply_to_message else None
            )
            
            # Check if bot should respond
            should_respond = await self._should_respond_to_message(update, context)
            logger.debug(f"Should respond to message: {should_respond}")
            
            if should_respond:
                logger.info(f"Bot responding to message: {message.text[:50]}...")
                
                # Get conversation context
                context_messages = await self.db_service.get_recent_messages(
                    group_id=chat_id,
                    limit=config.context_messages_count
                )
                
                # Process with AI
                response = await self._process_with_ai(
                    message=message.text,
                    context_messages=context_messages,
                    user_id=user_id,
                    chat_id=chat_id
                )
                
                if response:
                    sent_message = await message.reply_text(response)
                    
                    # Log bot's response
                    await self.db_service.log_conversation(
                        group_id=chat_id,
                        user_id=context.bot.id,
                        message_id=sent_message.message_id,
                        message_text=response,
                        is_bot_message=True,
                        is_reply=True,
                        reply_to_message_id=message.message_id
                    )
                    logger.info("Bot response sent successfully")
                else:
                    logger.warning("AI processing returned empty response")
            else:
                logger.debug("Bot will not respond to this message")
                
        except Exception as e:
            logger.error(f"Error handling group message: {e}")
            # Don't send error to user in group to avoid spam
    
    async def _handle_private_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle private messages."""
        message = update.message
        user_id = update.effective_user.id
        
        # Process with AI (no context needed for private messages)
        response = await self._process_with_ai(
            message=message.text,
            context_messages=[],
            user_id=user_id,
            chat_id=update.effective_chat.id
        )
        
        if response:
            await message.reply_text(response)
    
    async def _should_respond_to_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Determine if the bot should respond to a message."""
        message = update.message
        
        # Log for debugging
        logger.debug(f"Checking if should respond to message: {message.text[:50]}...")
        
        # Check if bot is mentioned using entities
        if message.entities:
            for entity in message.entities:
                if entity.type == "mention":
                    mentioned_username = message.text[entity.offset:entity.offset + entity.length]
                    logger.debug(f"Found mention: {mentioned_username}")
                    if mentioned_username == f"@{config.bot_username}":
                        logger.debug("Bot mentioned via @username")
                        return True
                elif entity.type == "text_mention":
                    # Handle text mentions (when user doesn't have username)
                    if hasattr(entity, 'user') and entity.user.id == context.bot.id:
                        logger.debug("Bot mentioned via text mention")
                        return True
        
        # Check if bot username is mentioned anywhere in the message (case insensitive)
        if config.bot_username and config.bot_username.lower() in message.text.lower():
            logger.debug("Bot username found in message text")
            return True
        
        # Check if this is a reply to bot's message
        if message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
            logger.debug("Message is reply to bot")
            return True
        
        # Check if message starts with bot's first name (common way to address bots)
        bot_me = await context.bot.get_me()
        if bot_me.first_name and bot_me.first_name.lower() in message.text.lower():
            logger.debug("Bot first name found in message")
            return True
        
        logger.debug("Should not respond to this message")
        return False
    
    async def _process_with_ai(self, message: str, context_messages: List[Dict], user_id: int, chat_id: int) -> Optional[str]:
        """Process message with AI and handle different intents."""
        try:
            # Get group settings
            group_settings = await self.db_service.get_group_settings(chat_id)
            
            # Analyze intent with AI
            intent_analysis = await self.gemini_service.analyze_intent(
                message=message,
                context_messages=context_messages,
                temperature=group_settings.temperature,
                tone=group_settings.tone
            )
            
            # Handle different intents
            if intent_analysis.get("intent") == "save_info":
                return await self._handle_save_info(intent_analysis, user_id, chat_id)
            elif intent_analysis.get("intent") == "retrieve_info":
                return await self._handle_retrieve_info(intent_analysis, chat_id)
            elif intent_analysis.get("intent") == "summarize":
                return await self._handle_summarize(intent_analysis, chat_id)
            else:
                # Regular conversation
                return await self.gemini_service.generate_response(
                    message=message,
                    context_messages=context_messages,
                    temperature=group_settings.temperature,
                    tone=group_settings.tone
                )
        
        except Exception as e:
            logger.error(f"Error processing message with AI: {e}")
            return "Xin lỗi, tôi gặp lỗi khi xử lý tin nhắn của bạn. Vui lòng thử lại."
    
    async def _handle_save_info(self, intent_analysis: Dict, user_id: int, chat_id: int) -> str:
        """Handle information saving requests."""
        try:
            key = intent_analysis.get("key")
            value = intent_analysis.get("value")
            
            if not key or not value:
                return "Tôi không hiểu thông tin nào bạn muốn tôi lưu. Vui lòng nói cụ thể hơn."
            
            # Save the information
            await self.db_service.save_user_info(user_id, key, value)
            
            return f"✅ Tôi đã lưu {key} của bạn: {value}"
        
        except Exception as e:
            logger.error(f"Error saving user info: {e}")
            return "Xin lỗi, tôi không thể lưu thông tin đó. Vui lòng thử lại."
    
    async def _handle_retrieve_info(self, intent_analysis: Dict, chat_id: int) -> str:
        """Handle information retrieval requests."""
        try:
            key = intent_analysis.get("key")
            target_username = intent_analysis.get("target_username")
            
            if not key:
                return "Tôi không hiểu thông tin nào bạn đang tìm kiếm. Vui lòng nói cụ thể hơn."
            
            # Retrieve the information
            info = await self.db_service.get_user_info_by_username(target_username, key)
            
            if info:
                return f"📋 {key} của {target_username}: {info.value}"
            else:
                return f"Tôi không có thông tin đó cho {target_username}."
        
        except Exception as e:
            logger.error(f"Error retrieving user info: {e}")
            return "Xin lỗi, tôi không thể lấy thông tin đó. Vui lòng thử lại."
    
    async def _handle_summarize(self, intent_analysis: Dict, chat_id: int) -> str:
        """Handle conversation summarization requests."""
        try:
            message_count = intent_analysis.get("message_count", 20)
            
            # Get recent messages
            messages = await self.db_service.get_recent_messages(chat_id, message_count)
            
            if not messages:
                return "Không có tin nhắn gần đây nào để tóm tắt."
            
            # Generate summary
            summary = await self.gemini_service.summarize_conversation(messages)
            
            return f"📝 **Tóm tắt cuộc trò chuyện:**\n\n{summary}"
        
        except Exception as e:
            logger.error(f"Error summarizing conversation: {e}")
            return "Xin lỗi, tôi không thể tóm tắt cuộc trò chuyện. Vui lòng thử lại."
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /settings command (admin only)."""
        # Check if this is a group chat
        if update.effective_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            await update.message.reply_text("Cài đặt chỉ có thể được sử dụng trong nhóm chat.")
            return
        
        # Check if user is admin
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        try:
            chat_member = await context.bot.get_chat_member(chat_id, user_id)
            if chat_member.status not in ["administrator", "creator"]:
                await update.message.reply_text("Chỉ quản trị viên nhóm mới có thể sử dụng lệnh này.")
                return
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            await update.message.reply_text("Lỗi khi kiểm tra quyền.")
            return
        
        # Show settings menu
        await self._show_settings_menu(update, context)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current bot status and configuration."""
        chat_id = update.effective_chat.id
        
        try:
            # Get current settings
            if update.effective_chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                settings = await self.db_service.get_group_settings(chat_id)
                
                # Map tone to Vietnamese
                tone_mapping = {
                    "friendly": "Thân thiện",
                    "professional": "Chuyên nghiệp", 
                    "humorous": "Hài hước",
                    "serious": "Nghiêm túc",
                    "flattering": "Nịnh nọt",
                    "casual": "Thoải mái",
                    "formal": "Hiền triết"
                }
                vietnamese_tone = tone_mapping.get(settings.tone, settings.tone.title())
                
                status_text = f"""
🤖 **Trạng thái Bot**

**Cấu hình hiện tại:**
• **Mô hình AI**: {settings.gemini_model}
• **Mức độ sáng tạo**: {settings.temperature}
• **Giọng điệu**: {vietnamese_tone}
• **Tin nhắn ngữ cảnh**: {settings.context_messages_count}
• **Trạng thái**: {'Hoạt động' if settings.is_active else 'Không hoạt động'}

**Kích hoạt Bot:**
• Nhắc đến tôi: @{config.bot_username}
• Trả lời tin nhắn của tôi
• Sử dụng /settings (chỉ quản trị viên)

**Khả năng:**
• 💾 Lưu trữ & truy xuất thông tin
• 🧠 Trò chuyện theo ngữ cảnh
• 📊 Tóm tắt tin nhắn
• ⚙️ Cấu hình quản trị
"""
            else:
                status_text = f"""
🤖 **Trạng thái Bot**

**Chế độ chat riêng**
• Tất cả tin nhắn đều được xử lý
• Không có cài đặt nhóm riêng
• Đầy đủ khả năng AI

**Tên người dùng**: @{config.bot_username}
**Mô hình**: {config.gemini_model}
"""
            
            await update.message.reply_text(
                status_text,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error showing status: {e}")
            await update.message.reply_text("Lỗi khi lấy trạng thái bot.")
    
    async def test_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Test command to verify bot is working."""
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        try:
            # Get bot info
            bot_info = await context.bot.get_me()
            
            test_text = f"""
🧪 **Kiểm tra Bot**

✅ **Tôi đang hoạt động!**

**Thông tin Bot:**
• **Tên người dùng**: @{bot_info.username}
• **Tên**: {bot_info.first_name}
• **ID**: {bot_info.id}

**Thông tin Chat:**
• **Loại Chat**: {update.effective_chat.type}
• **ID Chat**: {chat_id}
• **ID của bạn**: {user_id}
"""
            
            if update.effective_chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                test_text += f"""
**Đối với nhóm chat:**
• Thử nhắc đến tôi: @{bot_info.username}
• Thử trả lời tin nhắn này
• Thử nói tên tôi: {bot_info.first_name}
• Sử dụng /settings để cấu hình (chỉ quản trị viên)
"""
            else:
                test_text += f"""
**Đối với chat riêng:**
• Tôi trả lời tất cả tin nhắn
• Không cần nhắc đến
• Đầy đủ khả năng AI
"""
            
            await update.message.reply_text(
                test_text,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error in test command: {e}")
            await update.message.reply_text("❌ Kiểm tra thất bại. Kiểm tra logs của bot để biết chi tiết.")
    
    async def _show_settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show the settings menu with inline keyboard."""
        keyboard = [
            [InlineKeyboardButton("🤖 Mô hình AI", callback_data="setting_model")],
            [InlineKeyboardButton("🎨 Mức độ sáng tạo", callback_data="setting_temperature")],
            [InlineKeyboardButton("🎭 Giọng điệu", callback_data="setting_tone")],
            [InlineKeyboardButton("💬 Tin nhắn ngữ cảnh", callback_data="setting_context")],
            [InlineKeyboardButton("❌ Đóng", callback_data="setting_close")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🛠️ **Cài đặt Bot**\n\n"
            "Chọn những gì bạn muốn cấu hình:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _show_settings_menu_edit(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Show the settings menu by editing existing message."""
        keyboard = [
            [InlineKeyboardButton("🤖 Mô hình AI", callback_data="setting_model")],
            [InlineKeyboardButton("🎨 Mức độ sáng tạo", callback_data="setting_temperature")],
            [InlineKeyboardButton("🎭 Giọng điệu", callback_data="setting_tone")],
            [InlineKeyboardButton("💬 Tin nhắn ngữ cảnh", callback_data="setting_context")],
            [InlineKeyboardButton("❌ Đóng", callback_data="setting_close")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🛠️ **Cài đặt Bot**\n\n"
            "Chọn những gì bạn muốn cấu hình:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline keyboards."""
        query = update.callback_query
        await query.answer()
        
        # Handle settings callbacks
        if query.data.startswith("setting_"):
            await self._handle_settings_callback(query, context)
        elif query.data == "setting_back":
            await self._show_settings_menu_edit(query, context)
    
    async def _handle_settings_callback(self, query, context):
        """Handle settings-related callback queries."""
        action = query.data.replace("setting_", "")
        chat_id = query.message.chat.id
        
        if action == "close":
            await query.edit_message_text("Menu cài đặt đã đóng.")
            return
        
        if action == "model":
            await self._show_model_selection(query, context)
        elif action == "temperature":
            await self._show_temperature_selection(query, context)
        elif action == "tone":
            await self._show_tone_selection(query, context)
        elif action == "context":
            await self._show_context_selection(query, context)
        elif action.startswith("set_"):
            await self._handle_setting_update(query, context)
        else:
            await query.edit_message_text(f"Unknown setting: {action}")
    
    async def _show_model_selection(self, query, context):
        """Show AI model selection menu."""
        keyboard = [
            [InlineKeyboardButton("Gemini 2.5 Pro", callback_data="setting_set_model_gemini-2.5-pro")],
            [InlineKeyboardButton("Gemini 2.5 Flash", callback_data="setting_set_model_gemini-2.5-flash")],
            [InlineKeyboardButton("Gemini 2.0 Flash", callback_data="setting_set_model_gemini-2.0-flash")],
            [InlineKeyboardButton("🔙 Quay lại", callback_data="setting_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🤖 **Lựa chọn mô hình AI cho thầy Huấn**\n\n"
            "Chọn mô hình AI cho nhóm này:\n"
            "• **Gemini 2.5 Pro**: Mạnh nhất, phân tích sâu\n"
            "• **Gemini 2.5 Flash**: Cân bằng tốc độ & chất lượng\n"
            "• **Gemini 2.0 Flash**: Nhanh nhất, phù hợp chat thường",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _show_temperature_selection(self, query, context):
        """Show creativity/temperature selection menu."""
        keyboard = [
            [InlineKeyboardButton("🧊 Rất lôgic (0.1)", callback_data="setting_set_temperature_0.1")],
            [InlineKeyboardButton("🔧 Lôgic (0.3)", callback_data="setting_set_temperature_0.3")],
            [InlineKeyboardButton("⚖️ Cân bằng (0.7)", callback_data="setting_set_temperature_0.7")],
            [InlineKeyboardButton("🎨 Sáng tạo (0.9)", callback_data="setting_set_temperature_0.9")],
            [InlineKeyboardButton("🌟 Rất sáng tạo (1.0)", callback_data="setting_set_temperature_1.0")],
            [InlineKeyboardButton("🔙 Quay lại", callback_data="setting_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎨 **Mức độ sáng tạo của thầy Huấn**\n\n"
            "Chọn mức độ sáng tạo của thầy Huấn:\n"
            "• **Giá trị thấp**: Lôgic hơn, có thể dự đoán\n"
            "• **Giá trị cao**: Sáng tạo hơn, không dự đoán được",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _show_tone_selection(self, query, context):
        """Show tone selection menu."""
        keyboard = [
            [InlineKeyboardButton("😊 Thân thiện", callback_data="setting_set_tone_friendly")],
            [InlineKeyboardButton("💼 Chuyên nghiệp", callback_data="setting_set_tone_professional")],
            [InlineKeyboardButton("😄 Hài hước", callback_data="setting_set_tone_humorous")],
            [InlineKeyboardButton("🎩 Nghiêm túc", callback_data="setting_set_tone_serious")],
            [InlineKeyboardButton("💖 Nịnh nọt", callback_data="setting_set_tone_flattering")],
            [InlineKeyboardButton("👥 Thoải mái", callback_data="setting_set_tone_casual")],
            [InlineKeyboardButton("📋 Hiền triết", callback_data="setting_set_tone_formal")],
            [InlineKeyboardButton("🔙 Quay lại", callback_data="setting_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎭 **Giọng điệu của thầy Huấn**\n\n"
            "Chọn phong cách giao tiếp cho thầy Huấn:\n\n"
            "😊 **Thân thiện**: Gần gũi, ấm áp, hay dùng \"bạn\", \"mình\"\n"
            "💼 **Chuyên nghiệp**: Lịch sự, trang trọng, dùng \"anh/chị\"\n"
            "😄 **Hài hước**: Vui vẻ, hay đùa, dùng meme, emoji nhiều\n"
            "🎩 **Nghiêm túc**: Trang trọng, ít đùa, tập trung vào vấn đề\n"
            "💖 **Nịnh nọt**: Khen ngợi, gọi \"ông chủ/bà chủ/ngài\", xưng \"nô tỳ\"\n"
            "👥 **Thoải mái**: Bình dân, dùng \"m/t\", \"bro\", \"chị em\"\n"
            "📋 **Hiền triết**: Sâu sắc, triết lý, dùng thành ngữ, tục ngữ",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _show_context_selection(self, query, context):
        """Show context messages selection menu."""
        keyboard = [
            [InlineKeyboardButton("3 tin nhắn", callback_data="setting_set_context_3")],
            [InlineKeyboardButton("5 tin nhắn", callback_data="setting_set_context_5")],
            [InlineKeyboardButton("7 tin nhắn", callback_data="setting_set_context_7")],
            [InlineKeyboardButton("10 tin nhắn", callback_data="setting_set_context_10")],
            [InlineKeyboardButton("15 tin nhắn", callback_data="setting_set_context_15")],
            [InlineKeyboardButton("🔙 Quay lại", callback_data="setting_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "💬 **Tin nhắn ngữ cảnh cho thầy Huấn**\n\n"
            "Chọn số lượng tin nhắn gần đây mà thầy Huấn nên đọc để hiểu ngữ cảnh:\n"
            "• **Ít tin nhắn**: Nhanh hơn, ít ngữ cảnh hơn\n"
            "• **Nhiều tin nhắn**: Chậm hơn, ngữ cảnh tốt hơn",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _handle_setting_update(self, query, context):
        """Handle setting updates."""
        parts = query.data.split("_")
        if len(parts) < 4:
            await query.edit_message_text("Định dạng cài đặt không hợp lệ.")
            return
        
        setting_type = parts[2]  # model, temperature, tone, context
        setting_value = "_".join(parts[3:])  # the actual value
        chat_id = query.message.chat.id
        
        try:
            # Update the setting in database
            update_data = {}
            if setting_type == "model":
                update_data["gemini_model"] = setting_value
            elif setting_type == "temperature":
                update_data["temperature"] = float(setting_value)
            elif setting_type == "tone":
                update_data["tone"] = setting_value
            elif setting_type == "context":
                update_data["context_messages_count"] = int(setting_value)
            
            success = await self.db_service.update_group_settings(chat_id, **update_data)
            
            if success:
                # Create Vietnamese display names for settings
                setting_names = {
                    "model": "Mô hình AI",
                    "temperature": "Mức độ sáng tạo",
                    "tone": "Giọng điệu",
                    "context": "Tin nhắn ngữ cảnh"
                }
                
                # Create Vietnamese display values for tone
                tone_display = {
                    "friendly": "Thân thiện",
                    "professional": "Chuyên nghiệp",
                    "humorous": "Hài hước",
                    "serious": "Nghiêm túc",
                    "flattering": "Nịnh nọt",
                    "casual": "Thoải mái",
                    "formal": "Hiền triết"
                }
                
                display_name = setting_names.get(setting_type, setting_type.title())
                display_value = tone_display.get(setting_value, setting_value) if setting_type == "tone" else setting_value
                
                await query.edit_message_text(
                    f"✅ **Cài đặt đã được cập nhật**\n\n"
                    f"**{display_name}** của thầy Huấn đã được đặt thành: `{display_value}`\n\n"
                    f"Thay đổi sẽ có hiệu lực ngay lập tức.",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ Không thể cập nhật cài đặt. Vui lòng thử lại.")
                
        except Exception as e:
            logger.error(f"Error updating setting: {e}")
            await query.edit_message_text("❌ Lỗi khi cập nhật cài đặt. Vui lòng thử lại.")
    
    async def run(self):
        """Run the bot."""
        try:
            # Initialize the bot
            await self.initialize()
            
            logger.info("Starting bot...")
            # Use the asynchronous run_polling method
            await self.application.run_polling(allowed_updates=Update.ALL_TYPES)
        except Exception as e:
            logger.error(f"Error running bot: {e}")
            raise
        finally:
            # Ensure proper cleanup
            if self.application.running:
                await self.application.stop()
                await self.application.shutdown()

async def main():
    """Main function to run the bot."""
    # Configure logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=getattr(logging, config.log_level.upper())
    )
    
    # Create bot instance
    bot = TelegramBot()
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        # Create a task to stop the bot
        asyncio.create_task(shutdown_bot(bot))
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Run bot
        await bot.run()
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise
    finally:
        logger.info("Bot shutdown complete")

async def shutdown_bot(bot):
    """Gracefully shutdown the bot."""
    try:
        if bot.application and bot.application.running:
            await bot.application.stop()
            await bot.application.shutdown()
            logger.info("Bot stopped successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise 