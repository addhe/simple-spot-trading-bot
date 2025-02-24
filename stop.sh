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
        rm $PID_FILE
        echo "Bot $BOT_NAME telah dihentikan."
    else
        rm $PID_FILE
        echo "Bot $BOT_NAME tidak berjalan."
    fi
else
    echo "Bot $BOT_NAME tidak berjalan."
fi
