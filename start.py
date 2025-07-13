#!/usr/bin/env python3
"""
Telegram LLM Bot - Startup Script
This script helps you set up and run the Telegram bot with proper configuration.
"""

import os
import sys
import asyncio
from pathlib import Path

def check_python_version():
    """Check if Python version is compatible."""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required.")
        print(f"Current version: {sys.version}")
        return False
    print(f"✅ Python version: {sys.version}")
    return True

def check_dependencies():
    """Check if all required dependencies are installed."""
    required_packages = [
        'telegram',
        'google.generativeai',
        'dotenv',
        'sqlalchemy',
        'aiosqlite',
        'pydantic',
        'loguru'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"✅ {package}")
        except ImportError:
            missing_packages.append(package)
            print(f"❌ {package}")
    
    if missing_packages:
        print("\n💡 Install missing dependencies with:")
        print("pip install -r requirements.txt")
        return False
    
    return True

def check_env_file():
    """Check if .env file exists and has required variables."""
    env_file = Path('.env')
    
    if not env_file.exists():
        print("❌ .env file not found")
        print("\n📝 Please create a .env file with the following variables:")
        print_env_template()
        return False
    
    # Check required variables
    required_vars = [
        'TELEGRAM_BOT_TOKEN',
        'BOT_USERNAME',
        'GOOGLE_API_KEY'
    ]
    
    from dotenv import load_dotenv
    load_dotenv()
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("\n📝 Please add these to your .env file:")
        print_env_template()
        return False
    
    print("✅ .env file configured")
    return True

def print_env_template():
    """Print the .env file template."""
    template = """
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
BOT_USERNAME=your_bot_username_here

# Google Gemini AI Configuration
GOOGLE_API_KEY=your_google_gemini_api_key_here
GEMINI_MODEL=gemini-pro

# Database Configuration
DATABASE_URL=sqlite:///bot_data.db

# Bot Settings
DEFAULT_TEMPERATURE=0.7
DEFAULT_TONE=friendly
CONTEXT_MESSAGES_COUNT=7
DEBUG=false

# Logging
LOG_LEVEL=INFO
"""
    print(template)

def print_setup_instructions():
    """Print setup instructions for getting API keys."""
    print("\n🔧 Setup Instructions:")
    print("\n1. Get Telegram Bot Token:")
    print("   • Open Telegram and message @BotFather")
    print("   • Send /newbot command")
    print("   • Follow instructions to create your bot")
    print("   • Copy the bot token")
    print("   • Note your bot's username (without @)")
    
    print("\n2. Get Google Gemini API Key:")
    print("   • Go to https://makersuite.google.com/app/apikey")
    print("   • Sign in with your Google account")
    print("   • Create a new API key")
    print("   • Copy the API key")
    
    print("\n3. Create .env file:")
    print("   • Copy the template above")
    print("   • Replace the placeholder values")
    print("   • Save as .env in the project root")

async def test_bot_config():
    """Test if the bot configuration is working."""
    try:
        from config import config, validate_config
        validate_config()
        print("✅ Configuration validation passed")
        return True
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return False

async def main():
    """Main startup function."""
    print("🤖 Telegram LLM Bot - Startup Check")
    print("=" * 50)
    
    # Check Python version
    if not check_python_version():
        return
    
    print("\n📦 Checking Dependencies:")
    if not check_dependencies():
        return
    
    print("\n⚙️ Checking Configuration:")
    if not check_env_file():
        print_setup_instructions()
        return
    
    # Test configuration
    if not await test_bot_config():
        return
    
    print("\n✅ All checks passed! Starting bot...")
    print("=" * 50)
    
    # Import and run the bot
    try:
        from main import main as bot_main
        await bot_main()
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting bot: {e}")
        print("Check the logs for more details.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Startup error: {e}")
        sys.exit(1) 