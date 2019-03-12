#!/usr/bin/env bash

rm -rf ~/.local/share/nucypher

# Set Upgrade Secrets
export NUCYPHER_MINER_ESCROW_SECRET='debuggerdebugger'
export NUCYPHER_POLICY_MANAGER_SECRET='debuggerdebugger'
export NUCYPHER_USER_ESCROW_PROXY_SECRET='debuggerdebugger'

# Deploy Main Contracts
nucypher-deploy contracts --provider-uri ipc:///tmp/geth.ipc --poa

# Set Ursula Password
export NUCYPHER_KEYRING_PASSWORD='debuggerdebuggerdebugger'

# Initialize New Ursula
nucypher ursula init --provider-uri ipc:///tmp/geth.ipc --poa --network TEMPORARY_DOMAIN --rest-host 0.0.0.0

# Inline Staking
nucypher ursula stake --value 15000 --duration 30 --force

# View Active Stakes
nucypher ursula stake --list
