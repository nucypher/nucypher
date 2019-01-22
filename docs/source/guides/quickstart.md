# NuCypher Quickstart

## Install NuCypher

`$ pip install nucypher`

## Run a Federated-Only Development Ursula

`$ nucypher ursula run --dev --federated-only`

## Run a Geth-Connected Development Ursula

`$ geth --dev`
`$ nucypher ursula run --dev --provider-uri /tmp/geth.ipc`
