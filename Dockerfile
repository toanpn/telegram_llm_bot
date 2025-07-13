FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir pydantic-settings greenlet

# Copy application code
COPY . .

# Create directory for database
RUN mkdir -p /app/data

# Set environment for database location
ENV DATABASE_URL=sqlite:///data/bot_data.db

# Create non-root user for security
RUN adduser --disabled-password --gecos '' appuser
RUN chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import requests; requests.get('https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe')" || exit 1

# Run the bot
CMD ["python3", "main.py"] 