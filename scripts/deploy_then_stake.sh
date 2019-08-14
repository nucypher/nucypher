#!/usr/bin/env bash

rm -rf ~/.local/share/nucypher

# Set Upgrade Secrets
export NUCYPHER_STAKING_ESCROW_SECRET='debuggerdebugger'
export NUCYPHER_POLICY_MANAGER_SECRET='debuggerdebugger'
export NUCYPHER_USER_ESCROW_PROXY_SECRET='debuggerdebugger'
export NUCYPHER_ADJUDICATOR_SECRET='debuggerdebugger'

# Deploy Main Contracts
nucypher-deploy contracts --provider ipc:///tmp/geth.ipc --poa

# Set Ursula Password
export NUCYPHER_KEYRING_PASSWORD='debuggerdebuggerdebugger'

# Initialize New Ursula
nucypher ursula init --provider ipc:///tmp/geth.ipc --poa --network TEMPORARY_DOMAIN --rest-host 0.0.0.0

# Inline Staking
nucypher ursula stake --value 15000 --lock_periods 30 --force

# View Active Stakes
nucypher ursula stake --list
