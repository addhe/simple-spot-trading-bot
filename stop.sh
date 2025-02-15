#!/bin/bash

# Configuration
BOT_NAME="crypto_bot"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/$BOT_NAME.pid"

# Function to check if a process exists
check_process() {
    ps -p $1 > /dev/null 2>&1
}

# Check if PID file exists
if [ ! -f "$PID_FILE" ]; then
    echo "Bot is not running (no PID file found)"
    exit 0
fi

# Read PID from file
PID=$(cat "$PID_FILE")

# Check if process is running
if check_process $PID; then
    echo "Stopping bot with PID $PID..."

    # Try graceful shutdown first
    kill -TERM $PID

    # Wait for up to 10 seconds for graceful shutdown
    for i in {1..10}; do
        if ! check_process $PID; then
            echo "Bot stopped successfully"
            rm -f "$PID_FILE"
            exit 0
        fi
        sleep 1
    done

    # Force kill if still running
    echo "Bot did not stop gracefully, forcing shutdown..."
    kill -9 $PID

    # Final check
    if ! check_process $PID; then
        echo "Bot was forcefully stopped"
    else
        echo "Failed to stop bot"
        exit 1
    fi
else
    echo "Bot is not running (PID $PID not found)"
fi

# Clean up PID file
rm -f "$PID_FILE"
