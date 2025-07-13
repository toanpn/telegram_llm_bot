#!/usr/bin/env python3
"""
Test script for the Telegram LLM Bot
This script tests various components of the bot to ensure they work correctly.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

async def test_config():
    """Test configuration loading."""
    print("Testing configuration...")
    try:
        from config import config, validate_config
        print(f"✅ Configuration loaded")
        print(f"  - Bot username: {config.bot_username}")
        print(f"  - Gemini model: {config.gemini_model}")
        print(f"  - Database URL: {config.database_url}")
        print(f"  - Default temperature: {config.default_temperature}")
        print(f"  - Default tone: {config.default_tone}")
        return True
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return False

async def test_database():
    """Test database initialization."""
    print("\nTesting database...")
    try:
        from database_service import DatabaseService
        
        db_service = DatabaseService()
        await db_service.initialize()
        
        # Test user creation
        user = await db_service.get_or_create_user(
            telegram_id=123456,
            username="testuser",
            first_name="Test",
            last_name="User"
        )
        print(f"✅ Database working - Created user: {user.username}")
        
        # Test info storage
        success = await db_service.save_user_info(123456, "test_key", "test_value")
        if success:
            print("✅ User info storage working")
        else:
            print("❌ User info storage failed")
        
        # Test info retrieval
        info = await db_service.get_user_info(123456, "test_key")
        if info and info.value == "test_value":
            print("✅ User info retrieval working")
        else:
            print("❌ User info retrieval failed")
        
        return True
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

async def test_gemini():
    """Test Gemini AI service."""
    print("\nTesting Gemini AI service...")
    try:
        from gemini_service import GeminiService
        
        service = GeminiService()
        
        # Test intent analysis
        intent = await service.analyze_intent(
            message="save my email test@example.com",
            context_messages=[]
        )
        print(f"✅ Intent analysis working - Intent: {intent.get('intent')}")
        
        # Test response generation
        response = await service.generate_response(
            message="Hello, how are you?",
            context_messages=[]
        )
        print(f"✅ Response generation working - Response: {response[:50]}...")
        
        return True
    except Exception as e:
        print(f"❌ Gemini AI error: {e}")
        return False

async def test_models():
    """Test database models."""
    print("\nTesting database models...")
    try:
        from models import User, UserInfo, GroupSettings, ConversationLog
        
        # Test model creation
        user = User(
            telegram_id=789012,
            username="testmodel",
            first_name="Test",
            last_name="Model"
        )
        
        user_info = UserInfo(
            user_id=1,
            key="test_key",
            value="test_value"
        )
        
        group_settings = GroupSettings(
            group_id=-123456,
            gemini_model="gemini-pro",
            temperature=0.7,
            tone="friendly"
        )
        
        conversation_log = ConversationLog(
            group_id=-123456,
            user_id=789012,
            message_id=1,
            message_text="Test message"
        )
        
        print("✅ Database models working")
        return True
    except Exception as e:
        print(f"❌ Models error: {e}")
        return False

async def main():
    """Run all tests."""
    print("🧪 Testing Telegram LLM Bot Components")
    print("=" * 50)
    
    results = []
    
    # Test configuration
    results.append(await test_config())
    
    # Test models
    results.append(await test_models())
    
    # Test database
    results.append(await test_database())
    
    # Test Gemini (only if API key is configured)
    if os.getenv("GOOGLE_API_KEY"):
        results.append(await test_gemini())
    else:
        print("\n⚠️  Skipping Gemini tests (no API key configured)")
    
    print("\n" + "=" * 50)
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print("✅ All tests passed!")
        print("🚀 Your bot is ready to run!")
    else:
        print(f"❌ {total - passed} tests failed out of {total}")
        print("Please check the errors above and fix them before running the bot.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Test runner error: {e}")
        sys.exit(1) 