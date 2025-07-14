#!/bin/bash

echo "🐳 Setting up Docker Compose for Telegram Bot"
echo ""

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file..."
    cat > .env << 'ENVEOF'
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
BOT_USERNAME=your_bot_username_here

# Google Gemini AI Configuration
GOOGLE_API_KEY=your_google_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# Database Configuration
DATABASE_URL=sqlite:///data/bot_data.db

# Bot Settings
DEFAULT_TEMPERATURE=0.7
DEFAULT_TONE=friendly
CONTEXT_MESSAGES_COUNT=7
DEBUG=false

# Logging
LOG_LEVEL=INFO
ENVEOF

    echo "✅ .env file created!"
    echo ""
    echo "🔑 Please edit the .env file and add your API keys:"
    echo "   • TELEGRAM_BOT_TOKEN (get from @BotFather on Telegram)"
    echo "   • BOT_USERNAME (your bot's username without @)"
    echo "   • GOOGLE_API_KEY (get from https://makersuite.google.com/app/apikey)"
    echo ""
    echo "After editing .env, run: docker-compose up -d"
else
    echo "✅ .env file already exists"
    echo "🚀 Running docker-compose up..."
    docker-compose up -d
fi
