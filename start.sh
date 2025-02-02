#!/bin/bash

# Nama proses bot
BOT_NAME="crypto_bot"

# Direktori tempat skrip main.py berada
SCRIPT_DIR="/root/simple-spot-trading-bot-dev"

# Jalankan bot di latar belakang dan simpan PID ke file
nohup python3 $SCRIPT_DIR/main.py > $SCRIPT_DIR/bot.log 2>&1 &
echo $! > $SCRIPT_DIR/$BOT_NAME.pid

echo "Bot $BOT_NAME started with PID $(cat $SCRIPT_DIR/$BOT_NAME.pid)"
