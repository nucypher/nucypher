#!/usr/bin/env bash

virtualenv -p python3 .venv
source .venv/bin/activate
pip3 install -r requirements.txt
wget https://github.com/ethereum/solidity/releases/download/v0.4.16/solc-static-linux -O .venv/bin/solc
chmod +x .venv/bin/solc
