#!/bin/bash

# Nama proses bot
BOT_NAME="crypto_bot"

# Direktori tempat skrip main.py berada
SCRIPT_DIR="/root/simple-spot-trading-bot"

# Jalankan bot di latar belakang dan simpan PID ke file
nohup python3 $SCRIPT_DIR/main.py > $SCRIPT_DIR/logs/bot/bot.out 2>&1 &
echo $! > $SCRIPT_DIR/$BOT_NAME.pid
echo "Bot trading dimulai dengan PID $(cat $SCRIPT_DIR/$BOT_NAME.pid)"
