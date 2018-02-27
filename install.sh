#!/usr/bin/env bash

# System
sudo apt install build-essential automake pkg-config libtool libffi-dev libgmp-dev python3-pip

sudo pip3 install pipenv
pipenv --three
VENV="$(pipenv --venv)"

# Sol - TODO: integrity
wget https://github.com/ethereum/solidity/releases/download/v0.4.20/solc-static-linux -O "${VENV}/bin/solc"
chmod +x "${VENV}/bin/solc"

# Python
pipenv run pip3 install -e .
pipenv install --dev

#Populus
export PYTEST_POPULUS_PROJECT="./nkms_eth/project/"