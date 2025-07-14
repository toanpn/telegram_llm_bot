# Telegram LLM Bot

An intelligent Telegram bot that understands natural language and remembers conversations. Built with Google Gemini AI, it can save and retrieve information, summarize discussions, and adapt its personality to match your group's style.

## What It Does

**Smart Conversations**: The bot understands context from recent messages and responds naturally. No need to remember commands - just talk to it like you would a colleague.

**Memory Assistant**: Ask it to remember information like "save my email: john@example.com" and later retrieve it with "what's John's email?" - all in plain English.

**Meeting Helper**: Need a quick summary? Just ask "summarize our last discussion" and get a clean overview of what was talked about.

**Customizable**: Group admins can adjust the bot's personality, creativity level, and behavior through a simple settings menu.

## Quick Start

### Getting Your API Keys

1. **Telegram Bot**: Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, and follow the instructions
2. **Google Gemini**: Visit [Google AI Studio](https://makersuite.google.com/app/apikey) and create an API key

### Local Setup

```bash
# Clone and setup
git clone <your-repo-url>
cd telegram_bot
pip install -r requirements.txt pydantic-settings greenlet

# Configure your bot
cp .env.example .env
# Edit .env with your API keys

# Run it
python3 start.py
```

### Using the Bot

Add your bot to a group or message it directly. The bot only responds when:
- You mention it: `@your_bot_name hello there`
- You reply to one of its messages

**Try these examples:**
- `@bot remember my phone: 555-0123`
- `@bot what's Alice's email address?`
- `@bot summarize our conversation`
- `/settings` (for group admins)

## Deployment

### Option 1: Docker (Recommended)

```bash
# Quick start with Docker
docker-compose up -d

# Check if it's running
docker-compose logs -f
```

The database automatically persists across restarts using Docker volumes.

### Option 2: Production on EC2

Set up GitHub Actions for automatic deployment:

1. Fork this repository
2. Add these secrets in GitHub Settings:
   - `TELEGRAM_BOT_TOKEN`, `BOT_USERNAME`, `GOOGLE_API_KEY`
   - `DOCKER_USERNAME`, `DOCKER_PASSWORD` (Docker Hub)
   - `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY` (your server)
3. Push to main branch - automatic deployment starts!

### Option 3: Manual Deployment

Use the included deployment script:
```bash
export TELEGRAM_BOT_TOKEN="your_token"
export GOOGLE_API_KEY="your_key"
# ... other variables
./deploy.sh prod
```

## Configuration

Create a `.env` file with your settings:

```env
TELEGRAM_BOT_TOKEN=your_telegram_token
BOT_USERNAME=your_bot_username
GOOGLE_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-2.5-flash
DEFAULT_TONE=friendly
```

**Available tones**: friendly, professional, humorous, serious, flattering, casual, formal

## Maintenance

**View logs**: `docker-compose logs -f`  
**Update bot**: `docker-compose pull && docker-compose up -d`  
**Backup data**: `docker run --rm -v telegram_bot_bot_data:/data alpine tar czf /backup/backup.tar.gz -C /data .`

## Technical Details

- **Language**: Python 3.12
- **AI**: Google Gemini 2.5 Flash
- **Database**: SQLite with automatic persistence
- **Security**: Non-root container, environment variables, health checks
- **Architecture**: Async/await for performance, modular design

The bot stores user information, conversation history, and group settings in a SQLite database that automatically persists across restarts and deployments.

## Project Structure

```
telegram_bot/
├── main.py                 # Main application
├── config.py              # Configuration management  
├── models.py              # Database models
├── gemini_service.py      # AI integration
├── database_service.py    # Data persistence
├── Dockerfile             # Container configuration
├── docker-compose.yml     # Service orchestration
└── deploy.sh             # Deployment script
```

## Contributing

Found a bug or have an idea? Open an issue or submit a pull request. The codebase is designed to be easy to understand and extend.

## License

Open source - feel free to use and modify for your needs.
