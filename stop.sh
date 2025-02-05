#!/bin/bash

# Nama proses bot
BOT_NAME="crypto_bot"

# Direktori tempat skrip main.py berada
SCRIPT_DIR="/root/simple-spot-trading-bot"

# Baca PID dari file
PID_FILE="$SCRIPT_DIR/$BOT_NAME.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null; then
        kill $PID
        echo "Bot $BOT_NAME with PID $PID stopped"
        rm "$PID_FILE"
    else
        echo "Bot $BOT_NAME with PID $PID is not running"
        rm "$PID_FILE"
    fi
else
    echo "Bot $BOT_NAME is not running"
fi
