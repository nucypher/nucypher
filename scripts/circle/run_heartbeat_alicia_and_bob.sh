#!/usr/bin/env bash

# Run Alicia
echo "Starting Alicia..."
python3 /code/examples/heartbeat_demo/alicia.py 172.29.1.3:11500

# Run Dr. Bob
echo "Starting Bob..."
python3 /code/examples/heartbeat_demo/doctor.py 172.29.1.3:11500
