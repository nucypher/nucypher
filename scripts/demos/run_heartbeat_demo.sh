#!/usr/bin/env bash

echo "Starting Up Heartbeat Demo Test..."

# Start Local Fleet
"${0%/*}"/../local_fleet/run_local_fleet.sh

# Move to examples directory
cd "${0%/*}"/../../examples/heartbeat_demo/cli

# Run Alicia
echo "Starting Alicia..."
python3 alicia.py

# Run Dr. Bob
echo "Starting Bob..."
python3 doctor.py
