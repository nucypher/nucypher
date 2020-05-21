#!/usr/bin/env bash

mkdir ./bootnode

# Create a bootnode
bootnode --genkey ./bootnode/bootnode.key --verbosity 6
bootnode --nodekey ./bootnode/bootnode.key --writeaddress

# Run Bootnode
bootnode --nodekey ./bootnode/bootnode.key --verbosity 6
