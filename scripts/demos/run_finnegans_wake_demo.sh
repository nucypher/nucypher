#!/usr/bin/env bash

echo "Starting Up Finnegans Wake Demo Test..."

# Start local Ursula fleet
"${0%/*}"/../local_fleet/run_local_fleet.sh

# Move to demo directory
cd "${0%/*}"/../../examples/finnegans_wake_demo/

# Run demo
echo "Starting Demo"
python3 finnegans-wake-demo-federated.py
