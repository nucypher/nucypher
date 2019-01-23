# NuCypher Quickstart

## Install NuCypher

```bash
$ pip install nucypher
```

## Run a Federated-Only Development Ursula

```bash
$ nucypher ursula run --dev --federated-only
```

## Run a Geth-Connected Development Ursula

Run a local geth node in development mode:

```bash
$ geth --dev
```

Run a local development Ursula connected to the geth node

```bash
$ nucypher ursula run --dev --provider-uri /tmp/geth.ipc --checksum-address <GETH_ADDRESS>
```

Replace `<GETH_ADDRESS>` with the geth node's public checksum address.
