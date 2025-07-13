import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from typing import Optional

# Load environment variables
load_dotenv()

class Config(BaseSettings):
    """Configuration settings for the Telegram bot."""
    
    # Telegram Bot Configuration
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    bot_username: str = os.getenv("BOT_USERNAME", "")
    
    # Google Gemini AI Configuration
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    # Database Configuration
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///bot_data.db")
    
    # Bot Settings
    default_temperature: float = float(os.getenv("DEFAULT_TEMPERATURE", "0.7"))
    default_tone: str = os.getenv("DEFAULT_TONE", "friendly")
    context_messages_count: int = int(os.getenv("CONTEXT_MESSAGES_COUNT", "7"))
    
    # Debugging and Logging
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Global configuration instance
config = Config()

# Validation
def validate_config():
    """Validate that all required configuration is present."""
    missing_vars = []
    
    if not config.telegram_bot_token:
        missing_vars.append("TELEGRAM_BOT_TOKEN")
    
    if not config.google_api_key:
        missing_vars.append("GOOGLE_API_KEY")
    
    if not config.bot_username:
        missing_vars.append("BOT_USERNAME")
    
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    return True 