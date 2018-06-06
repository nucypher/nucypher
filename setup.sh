#!/bin/bash

PYTHON="python3.6"
SOLC_VER="0.4.24"

python3 -m pipenv > /dev/null
if [[ $? != 0 ]]
then
    echo "Installing pipenv in user directory..."
    pip3 install --user pipenv
fi

python3 -m pipenv install --python $PYTHON --dev
wget "https://github.com/ethereum/solidity/releases/download/v${SOLC_VER}/solc-static-linux" -O "$(pipenv --venv)/bin/solc"
chmod +x "$(pipenv --venv)/bin/solc"
pipenv run pip3 install -e .
