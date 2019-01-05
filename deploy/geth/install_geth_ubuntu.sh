#!/usr/bin/env bash

# Install Geth
sudo apt-get install software-properties-common -y
sudo add-apt-repository -y ppa:ethereum/ethereum
sudo apt-get update -y
sudo apt-get install ethereum -y

# Verify Installation
geth --version
