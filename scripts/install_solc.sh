#!/usr/bin/env bash


SOLC_VER="0.4.25"
SOL_BIN_PATH="$(pipenv --venv)/bin/solc"

echo "Downloading solidity compiler binary to: ${SOL_BIN_PATH}"
wget "https://github.com/ethereum/solidity/releases/download/v${SOLC_VER}/solc-static-linux" -O ${SOL_BIN_PATH}
echo "Setting executable permission on ${SOL_BIN_PATH}"
chmod +x ${SOL_BIN_PATH}
echo "Successfully Installed solc ${SOLC_VER}"
