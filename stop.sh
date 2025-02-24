#!/bin/bash

# Nama proses bot
BOT_NAME="crypto_bot"

# Direktori tempat skrip main.py berada
SCRIPT_DIR="/root/simple-spot-trading-bot"

# Baca PID dari file
PID=$(cat $SCRIPT_DIR/$BOT_NAME.pid)

# Hentikan proses dengan PID tersebut
if [ -n "$PID" ]; then
    kill -9 $PID
    rm $SCRIPT_DIR/$BOT_NAME.pid
    echo "Bot trading dengan PID $PID dihentikan"
else
    echo "Tidak ada proses bot trading yang berjalan"
fi
