#!/usr/bin/env bash

set -e
echo "Starting Local Development Fleet..."

# Boring Setup Stuff
rm -r /tmp/ursulas-logs | true
mkdir /tmp/ursulas-logs

# Set PATH
export PATH=~/.local/bin:$PATH
if [ -f ~/.bashrc ]; then
    source ~/.bashrc
fi

# Disable logging
export NUCYPHER_SENTRY_LOGS=0
export NUCYPHER_FILE_LOGS=0

# Run Node #1 (Lonely Ursula)
echo "Starting Lonely Ursula..."
python3 "${0%/*}"/../local_fleet/run_lonely_ursula.py > /tmp/ursulas-logs/ursula-11500.txt 2>&1 &
sleep 2

# Connect Node #2 to Lonely Ursula
echo "Starting Ursula #2..."
nucypher ursula run --debug --dev --federated-only --teacher localhost:11500 --rest-port 11501 > /tmp/ursulas-logs/ursula-11501.txt 2>&1 &
sleep 1

# Connect Node #3 to the local Fleet
echo "Starting Ursula #3..."
nucypher ursula run --debug --dev --federated-only --teacher localhost:11500 --rest-port 11502 > /tmp/ursulas-logs/ursula-11502.txt 2>&1 &
