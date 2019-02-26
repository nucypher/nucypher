#!/usr/bin/env bash

echo "Starting Up Heartbeat Demo Test..."

# Boring Setup Stuff
rm -r /tmp/ursulas-logs
mkdir /tmp/ursulas-logs

# Set PATH
export PATH=~/.local/bin:$PATH
source ~/.bashrc

# Disable logging
export NUCYPHER_SENTRY_LOGS=0
export NUCYPHER_FILE_LOGS=0

# Run Node #1 (Lonely Ursula)
echo "Starting Lonely Ursula..."
python3 ../run_lonely_demo_ursula.py > /tmp/ursulas-logs/ursula-11500.txt 2>&1 &
sleep 15

# Connect Node #2 to Lonely Ursula
echo "Starting Ursula #2..."
nucypher --debug ursula run --dev --federated-only --teacher-uri localhost:11500 --rest-port 11501 > /tmp/ursulas-logs/ursula-11501.txt 2>&1 &
sleep 15

# Connect Node #3 to the local Fleet
echo "Starting Ursula #3..."
nucypher --debug ursula run --dev --federated-only --teacher-uri localhost:11500 --rest-port 11502 > /tmp/ursulas-logs/ursula-11502.txt 2>&1 &
sleep 15

# Run Alicia
echo "Starting Alicia..."
python3 alicia.py
sleep 15

# Run Dr. Bob
echo "Starting Bob..."
python3 doctor.py

# Success
echo "Finished"
exit 0