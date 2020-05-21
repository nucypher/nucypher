#!/usr/bin/env bash

# Create custom blockchain storage area
rm -rf ./chaindata
mkdir ./chaindata

# Create an Account
echo $GETH_PASSWORD > ./password.txt

geth account new           \
     --datadir ./chaindata \
     --password ./password.txt

# Render the Genesis Template <-TODO

# Init the new blockchain
geth --datadir ./chaindata    \
     --identity "NuCypherTestnet"    \
     --networkid 112358       \
     init custom_genesis.json \
