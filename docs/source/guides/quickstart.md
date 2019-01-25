# NuCypher Quickstart

## Ursula

### Install NuCypher

```bash
$ pip3 install -U nucypher
```

### Run a Federated-Only Development Ursula

```bash
$ nucypher ursula run --dev --federated-only
```

### Configure a Persistent Ursula

```bash
$ nucypher ursula init --federated-only
```

### Run a Persistent Ursula

```bash
$ nucypher ursula run --teacher-uri <SEEDNODE_URI> --federated-only
```

Replace `<SEEDNODE_URI>` with the URI of a node running on the network and domain you want
to connect to (for example `0.0.0.0:9151` or `0xdeadbeef@0.0.0.0:9151`).

### Run a Geth-Connected Development Ursula

Run a local geth node in development mode:

```bash
$ geth --dev
```

Run a local development Ursula connected to the geth node

```bash
$ nucypher ursula run --dev --provider-uri /tmp/geth.ipc --checksum-address <GETH_ADDRESS>
```

Replace `<GETH_ADDRESS>` with the geth node's public checksum address.
