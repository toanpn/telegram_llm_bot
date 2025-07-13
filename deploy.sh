#!/bin/bash

# Telegram Bot Deployment Script
# Usage: ./deploy.sh [environment]
# Environment: dev, staging, prod (default: prod)

set -e

ENVIRONMENT=${1:-prod}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="telegram-llm-bot"

echo "🚀 Starting deployment for environment: $ENVIRONMENT"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if required files exist
check_files() {
    print_info "Checking required files..."
    
    if [ ! -f "Dockerfile" ]; then
        print_error "Dockerfile not found!"
        exit 1
    fi
    
    if [ ! -f "docker-compose.yml" ]; then
        print_error "docker-compose.yml not found!"
        exit 1
    fi
    
    if [ ! -f "requirements.txt" ]; then
        print_error "requirements.txt not found!"
        exit 1
    fi
    
    print_success "All required files found"
}

# Check if environment variables are set
check_env_vars() {
    print_info "Checking environment variables..."
    
    required_vars=(
        "TELEGRAM_BOT_TOKEN"
        "BOT_USERNAME"
        "GOOGLE_API_KEY"
        "EC2_HOST"
        "EC2_USERNAME"
        "EC2_SSH_KEY_PATH"
        "DOCKER_USERNAME"
    )
    
    missing_vars=()
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            missing_vars+=("$var")
        fi
    done
    
    if [ ${#missing_vars[@]} -ne 0 ]; then
        print_error "Missing required environment variables:"
        for var in "${missing_vars[@]}"; do
            echo "  - $var"
        done
        echo ""
        echo "Please set these variables in your environment or .env file"
        exit 1
    fi
    
    print_success "All required environment variables are set"
}

# Build Docker image
build_image() {
    print_info "Building Docker image..."
    
    local image_tag="$DOCKER_USERNAME/$PROJECT_NAME:$ENVIRONMENT"
    
    docker build -t "$image_tag" .
    
    if [ $? -eq 0 ]; then
        print_success "Docker image built successfully: $image_tag"
    else
        print_error "Failed to build Docker image"
        exit 1
    fi
}

# Push Docker image
push_image() {
    print_info "Pushing Docker image to registry..."
    
    local image_tag="$DOCKER_USERNAME/$PROJECT_NAME:$ENVIRONMENT"
    
    docker push "$image_tag"
    
    if [ $? -eq 0 ]; then
        print_success "Docker image pushed successfully"
    else
        print_error "Failed to push Docker image"
        exit 1
    fi
}

# Deploy to EC2
deploy_to_ec2() {
    print_info "Deploying to EC2 instance: $EC2_HOST"
    
    local image_tag="$DOCKER_USERNAME/$PROJECT_NAME:$ENVIRONMENT"
    
    # Create deployment script
    cat > /tmp/deploy_script.sh << EOF
#!/bin/bash
set -e

# Update system packages
sudo apt-get update

# Install Docker if not exists
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
    sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu \$(lsb_release -cs) stable"
    sudo apt-get update
    sudo apt-get install -y docker-ce
    sudo usermod -aG docker \$USER
fi

# Install Docker Compose if not exists
if ! command -v docker-compose &> /dev/null; then
    echo "Installing Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-\$(uname -s)-\$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# Create application directory
mkdir -p ~/telegram-bot-$ENVIRONMENT
cd ~/telegram-bot-$ENVIRONMENT

# Create .env file
cat > .env << ENVEOF
TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN
BOT_USERNAME=$BOT_USERNAME
GOOGLE_API_KEY=$GOOGLE_API_KEY
GEMINI_MODEL=gemini-1.5-flash
DATABASE_URL=sqlite:///data/bot_data.db
DEFAULT_TEMPERATURE=0.7
DEFAULT_TONE=friendly
CONTEXT_MESSAGES_COUNT=7
DEBUG=false
LOG_LEVEL=INFO
ENVEOF

# Create docker-compose.yml
cat > docker-compose.yml << COMPOSEEOF
version: '3.8'

services:
  telegram-bot:
    image: $image_tag
    container_name: telegram_llm_bot_$ENVIRONMENT
    restart: unless-stopped
    environment:
      - TELEGRAM_BOT_TOKEN=\\\${TELEGRAM_BOT_TOKEN}
      - BOT_USERNAME=\\\${BOT_USERNAME}
      - GOOGLE_API_KEY=\\\${GOOGLE_API_KEY}
      - GEMINI_MODEL=\\\${GEMINI_MODEL:-gemini-1.5-flash}
      - DATABASE_URL=sqlite:///data/bot_data.db
      - DEFAULT_TEMPERATURE=\\\${DEFAULT_TEMPERATURE:-0.7}
      - DEFAULT_TONE=\\\${DEFAULT_TONE:-friendly}
      - CONTEXT_MESSAGES_COUNT=\\\${CONTEXT_MESSAGES_COUNT:-7}
      - DEBUG=\\\${DEBUG:-false}
      - LOG_LEVEL=\\\${LOG_LEVEL:-INFO}
    volumes:
      - bot_data_$ENVIRONMENT:/app/data
      - bot_logs_$ENVIRONMENT:/app/logs
    networks:
      - bot_network_$ENVIRONMENT
    healthcheck:
      test: ["CMD", "python3", "-c", "import sqlite3; sqlite3.connect('/app/data/bot_data.db').close()"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  bot_data_$ENVIRONMENT:
    driver: local
  bot_logs_$ENVIRONMENT:
    driver: local

networks:
  bot_network_$ENVIRONMENT:
    driver: bridge
COMPOSEEOF

# Login to Docker Hub
echo "$DOCKER_PASSWORD" | sudo docker login -u "$DOCKER_USERNAME" --password-stdin

# Stop existing container
sudo docker-compose down || true

# Pull latest image
sudo docker-compose pull

# Start the bot
sudo docker-compose up -d

# Show status
echo "Deployment completed! Container status:"
sudo docker-compose ps
echo ""
echo "Recent logs:"
sudo docker-compose logs --tail=20
EOF
    
    # Copy and execute deployment script on EC2
    scp -i "$EC2_SSH_KEY_PATH" /tmp/deploy_script.sh "$EC2_USERNAME@$EC2_HOST:/tmp/"
    ssh -i "$EC2_SSH_KEY_PATH" "$EC2_USERNAME@$EC2_HOST" "chmod +x /tmp/deploy_script.sh && DOCKER_PASSWORD='$DOCKER_PASSWORD' /tmp/deploy_script.sh"
    
    if [ $? -eq 0 ]; then
        print_success "Deployment completed successfully!"
    else
        print_error "Deployment failed"
        exit 1
    fi
}

# Main deployment process
main() {
    print_info "Starting deployment process for $PROJECT_NAME ($ENVIRONMENT)"
    
    # Load environment variables if .env file exists
    if [ -f ".env" ]; then
        export $(cat .env | grep -v '^#' | xargs)
    fi
    
    check_files
    check_env_vars
    build_image
    push_image
    deploy_to_ec2
    
    print_success "🎉 Deployment completed successfully!"
    print_info "Your Telegram bot is now running on EC2!"
    print_info "You can check the logs with: ssh -i $EC2_SSH_KEY_PATH $EC2_USERNAME@$EC2_HOST 'cd ~/telegram-bot-$ENVIRONMENT && sudo docker-compose logs -f'"
}

# Run main function
main "$@" 