#!/bin/bash

# Configuration
BOT_NAME="crypto_bot"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs/bot"
PID_FILE="$SCRIPT_DIR/$BOT_NAME.pid"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Check if bot is already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null 2>&1; then
        echo "Bot is already running with PID $PID"
        exit 1
    else
        echo "Removing stale PID file"
        rm "$PID_FILE"
    fi
fi

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Start the bot
echo "Starting bot..."
nohup python main.py > "$LOG_DIR/bot.log" 2>&1 &
PID=$!

# Check if bot started successfully
sleep 2
if ps -p $PID > /dev/null 2>&1; then
    echo $PID > "$PID_FILE"
    echo "Bot started successfully with PID $PID"
    echo "Logs are available at $LOG_DIR/bot.log"
else
    echo "Failed to start bot. Check logs at $LOG_DIR/bot.log"
    exit 1
fi
