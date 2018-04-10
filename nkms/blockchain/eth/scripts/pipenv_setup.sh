#!/usr/bin/env bash

# System
read -p "Do you need to install system-wide dependencies [Y/N]? " yn
case $yn in
    [Yy]* )
        sudo apt install build-essential automake pkg-config libtool libffi-dev libgmp-dev python3-pip
        sudo pip3 install pipenv
        ;;
    * ) echo "Ok, we'll assume you installed them previously";;
esac

pipenv --three
VENV="$(pipenv --venv)"

# Sol - TODO: integrity
wget https://github.com/ethereum/solidity/releases/download/v0.4.21/solc-static-linux -O "${VENV}/bin/solc"
chmod +x "${VENV}/bin/solc"

# Python
pipenv run pip3 install -e .
pipenv install --dev

#Populus
echo "export PYTEST_POPULUS_PROJECT=\"$PWD/nkms_eth/project/\"" >> "${VENV}/bin/activate"
