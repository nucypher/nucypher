#!/usr/bin/env bash

set -e

if [[ "$OSTYPE" != "linux-gnu" ]]; then
    echo "This installation script is only compatible with linux-gnu-based operating systems."
    exit 0
fi

SOLC_VER="0.5.9"
SOL_BIN_PATH=~/.local/bin/solc

# Get solc binary for linux
echo "Downloading solidity compiler binary to: ${SOL_BIN_PATH}"
wget "https://github.com/ethereum/solidity/releases/download/v${SOLC_VER}/solc-static-linux" -O ${SOL_BIN_PATH}

# Set executable permission
echo "Setting executable permission on ${SOL_BIN_PATH}"
chmod +x ${SOL_BIN_PATH}

echo "Successfully Installed solc ${SOLC_VER}"
