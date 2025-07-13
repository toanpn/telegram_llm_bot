import asyncio
import logging
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
        
        # Add handlers
        self._add_handlers()
        
        logger.info("Bot initialized successfully")
    
    def _add_handlers(self):
        """Add message and command handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("settings", self.settings_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        
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
        
        if should_respond:
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
        
        # Check if bot is mentioned
        if message.entities:
            for entity in message.entities:
                if entity.type == "mention":
                    mentioned_username = message.text[entity.offset:entity.offset + entity.length]
                    if mentioned_username == f"@{config.bot_username}":
                        return True
        
        # Also check if bot username is mentioned anywhere in the message (case insensitive)
        if config.bot_username.lower() in message.text.lower():
            return True
        
        # Check if this is a reply to bot's message
        if message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
            return True
        
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
            return "Sorry, I encountered an error processing your message. Please try again."
    
    async def _handle_save_info(self, intent_analysis: Dict, user_id: int, chat_id: int) -> str:
        """Handle information saving requests."""
        try:
            key = intent_analysis.get("key")
            value = intent_analysis.get("value")
            
            if not key or not value:
                return "I couldn't understand what information you want me to save. Please be more specific."
            
            # Save the information
            await self.db_service.save_user_info(user_id, key, value)
            
            return f"✅ I've saved your {key}: {value}"
        
        except Exception as e:
            logger.error(f"Error saving user info: {e}")
            return "Sorry, I couldn't save that information. Please try again."
    
    async def _handle_retrieve_info(self, intent_analysis: Dict, chat_id: int) -> str:
        """Handle information retrieval requests."""
        try:
            key = intent_analysis.get("key")
            target_username = intent_analysis.get("target_username")
            
            if not key:
                return "I couldn't understand what information you're looking for. Please be more specific."
            
            # Retrieve the information
            info = await self.db_service.get_user_info_by_username(target_username, key)
            
            if info:
                return f"📋 {target_username}'s {key}: {info.value}"
            else:
                return f"I don't have that information for {target_username}."
        
        except Exception as e:
            logger.error(f"Error retrieving user info: {e}")
            return "Sorry, I couldn't retrieve that information. Please try again."
    
    async def _handle_summarize(self, intent_analysis: Dict, chat_id: int) -> str:
        """Handle conversation summarization requests."""
        try:
            message_count = intent_analysis.get("message_count", 20)
            
            # Get recent messages
            messages = await self.db_service.get_recent_messages(chat_id, message_count)
            
            if not messages:
                return "There are no recent messages to summarize."
            
            # Generate summary
            summary = await self.gemini_service.summarize_conversation(messages)
            
            return f"📝 **Conversation Summary:**\n\n{summary}"
        
        except Exception as e:
            logger.error(f"Error summarizing conversation: {e}")
            return "Sorry, I couldn't summarize the conversation. Please try again."
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /settings command (admin only)."""
        # Check if this is a group chat
        if update.effective_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            await update.message.reply_text("Settings can only be used in group chats.")
            return
        
        # Check if user is admin
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        try:
            chat_member = await context.bot.get_chat_member(chat_id, user_id)
            if chat_member.status not in ["administrator", "creator"]:
                await update.message.reply_text("Only group administrators can use this command.")
                return
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            await update.message.reply_text("Error checking permissions.")
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
                
                status_text = f"""
🤖 **Bot Status**

**Current Configuration:**
• **AI Model**: {settings.gemini_model}
• **Creativity Level**: {settings.temperature}
• **Tone**: {settings.tone.title()}
• **Context Messages**: {settings.context_messages_count}
• **Status**: {'Active' if settings.is_active else 'Inactive'}

**Bot Activation:**
• Mention me: @{config.bot_username}
• Reply to my messages
• Use /settings (admins only)

**Capabilities:**
• 💾 Information storage & retrieval
• 🧠 Contextual conversations
• 📊 Message summarization
• ⚙️ Admin configuration
"""
            else:
                status_text = f"""
🤖 **Bot Status**

**Private Chat Mode**
• All messages are processed
• No group-specific settings
• Full AI capabilities available

**My Username**: @{config.bot_username}
**Model**: {config.gemini_model}
"""
            
            await update.message.reply_text(
                status_text,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error showing status: {e}")
            await update.message.reply_text("Error retrieving bot status.")
    
    async def _show_settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show the settings menu with inline keyboard."""
        keyboard = [
            [InlineKeyboardButton("🤖 AI Model", callback_data="setting_model")],
            [InlineKeyboardButton("🎨 Creativity Level", callback_data="setting_temperature")],
            [InlineKeyboardButton("🎭 Tone of Voice", callback_data="setting_tone")],
            [InlineKeyboardButton("💬 Context Messages", callback_data="setting_context")],
            [InlineKeyboardButton("❌ Close", callback_data="setting_close")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🛠️ **Bot Settings**\n\n"
            "Choose what you'd like to configure:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _show_settings_menu_edit(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Show the settings menu by editing existing message."""
        keyboard = [
            [InlineKeyboardButton("🤖 AI Model", callback_data="setting_model")],
            [InlineKeyboardButton("🎨 Creativity Level", callback_data="setting_temperature")],
            [InlineKeyboardButton("🎭 Tone of Voice", callback_data="setting_tone")],
            [InlineKeyboardButton("💬 Context Messages", callback_data="setting_context")],
            [InlineKeyboardButton("❌ Close", callback_data="setting_close")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🛠️ **Bot Settings**\n\n"
            "Choose what you'd like to configure:",
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
            await query.edit_message_text("Settings menu closed.")
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
            [InlineKeyboardButton("Gemini Pro", callback_data="setting_set_model_gemini-pro")],
            [InlineKeyboardButton("Gemini Pro Vision", callback_data="setting_set_model_gemini-pro-vision")],
            [InlineKeyboardButton("🔙 Back", callback_data="setting_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🤖 **AI Model Selection**\n\n"
            "Choose the AI model for this group:\n"
            "• **Gemini Pro**: Best for text conversations\n"
            "• **Gemini Pro Vision**: Can analyze images",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _show_temperature_selection(self, query, context):
        """Show creativity/temperature selection menu."""
        keyboard = [
            [InlineKeyboardButton("🧊 Very Logical (0.1)", callback_data="setting_set_temperature_0.1")],
            [InlineKeyboardButton("🔧 Logical (0.3)", callback_data="setting_set_temperature_0.3")],
            [InlineKeyboardButton("⚖️ Balanced (0.7)", callback_data="setting_set_temperature_0.7")],
            [InlineKeyboardButton("🎨 Creative (0.9)", callback_data="setting_set_temperature_0.9")],
            [InlineKeyboardButton("🌟 Very Creative (1.0)", callback_data="setting_set_temperature_1.0")],
            [InlineKeyboardButton("🔙 Back", callback_data="setting_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎨 **Creativity Level**\n\n"
            "Choose how creative the bot should be:\n"
            "• **Lower values**: More logical, predictable\n"
            "• **Higher values**: More creative, unpredictable",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _show_tone_selection(self, query, context):
        """Show tone selection menu."""
        keyboard = [
            [InlineKeyboardButton("😊 Friendly", callback_data="setting_set_tone_friendly")],
            [InlineKeyboardButton("💼 Professional", callback_data="setting_set_tone_professional")],
            [InlineKeyboardButton("😄 Humorous", callback_data="setting_set_tone_humorous")],
            [InlineKeyboardButton("🎩 Serious", callback_data="setting_set_tone_serious")],
            [InlineKeyboardButton("💖 Flattering", callback_data="setting_set_tone_flattering")],
            [InlineKeyboardButton("👥 Casual", callback_data="setting_set_tone_casual")],
            [InlineKeyboardButton("📋 Formal", callback_data="setting_set_tone_formal")],
            [InlineKeyboardButton("🔙 Back", callback_data="setting_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎭 **Tone of Voice**\n\n"
            "Choose the bot's communication style:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _show_context_selection(self, query, context):
        """Show context messages selection menu."""
        keyboard = [
            [InlineKeyboardButton("3 messages", callback_data="setting_set_context_3")],
            [InlineKeyboardButton("5 messages", callback_data="setting_set_context_5")],
            [InlineKeyboardButton("7 messages", callback_data="setting_set_context_7")],
            [InlineKeyboardButton("10 messages", callback_data="setting_set_context_10")],
            [InlineKeyboardButton("15 messages", callback_data="setting_set_context_15")],
            [InlineKeyboardButton("🔙 Back", callback_data="setting_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "💬 **Context Messages**\n\n"
            "Choose how many recent messages the bot should read for context:\n"
            "• **Fewer messages**: Faster, less context\n"
            "• **More messages**: Slower, better context",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _handle_setting_update(self, query, context):
        """Handle setting updates."""
        parts = query.data.split("_")
        if len(parts) < 4:
            await query.edit_message_text("Invalid setting format.")
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
                await query.edit_message_text(
                    f"✅ **Setting Updated**\n\n"
                    f"**{setting_type.title()}** has been set to: `{setting_value}`\n\n"
                    f"The changes will take effect immediately.",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ Failed to update setting. Please try again.")
                
        except Exception as e:
            logger.error(f"Error updating setting: {e}")
            await query.edit_message_text("❌ Error updating setting. Please try again.")
    
    def run(self):
        """Run the bot."""
        # Create event loop for the main thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Initialize the bot
            loop.run_until_complete(self.initialize())
            
            logger.info("Starting bot...")
            # Use the synchronous run_polling method
            self.application.run_polling(allowed_updates=Update.ALL_TYPES)
        finally:
            # Clean up the loop
            loop.close()

def main():
    """Main function to run the bot."""
    # Configure logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=getattr(logging, config.log_level.upper())
    )
    
    # Create and run bot
    bot = TelegramBot()
    bot.run()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise 