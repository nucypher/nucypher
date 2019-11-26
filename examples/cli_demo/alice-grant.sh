#!/usr/bin/env bash
set -e

if [ $# != 1 ]; then
    echo "This script requires exactly one argument for policy label"
    exit 1
fi

# Setup Alice prefabricated keyring and ETH key
tar -xzf ~/nucypher/examples/cli_demo/alice.tar.gz -C ~
mkdir --parents ~/alice/known_nodes/metadata
mkdir ~/alice/known_nodes/certificates
mkdir --parents /tmp/cli-demo
cp ~/alice/alice-0xADA.eth ~/.ethereum/goerli/keystore

# Setup runtime environment
export NUCYPHER_KEYRING_PASSWORD=$TEST_ALICE_KEYRING_PASSWORD
export NUCYPHER_ALICE_ETH_PASSWORD=$TEST_ALICE_ETH_PASSWORD
ALICE_ETH_ADDRESS='0xADA16B764e8aa666120c7Ea6E339E66730C96674'
BOB_ENCRYPTING_KEY='02be9e3d9209194e2d9506ef45062e39a92bde3db8f53b417d89754236e8bf7e78'
BOB_VERIFYING_KEY='0350240f404ccf073509a6cf679f0582416f342cf796660bac963262052d8c8677'
TEACHER='discover.nucypher.network:9151'
LABEL=$1
EXPIRATION=$(python3 -c "import maya, datetime; print((maya.now() + datetime.timedelta(days=1)).iso8601())")

# Alice grants
nucypher alice grant \
    --teacher $TEACHER \
    --bob-verifying-key $BOB_VERIFYING_KEY \
    --bob-encrypting-key $BOB_ENCRYPTING_KEY \
    --label $LABEL \
    --expiration $EXPIRATION \
    --m 1 --n 1 --rate 1 \
    --config-file ~/alice/alice.json \
    --light \
    --json-ipc \
    | tee /tmp/grant.json

mv ~/.cache/nucypher/log/nucypher.log /tmp/cli-demo/alice.log
cp /tmp/grant.json /tmp/cli-demo

# Print the policy key to test correct format of grant output
cat /tmp/grant.json | python3 -c "import sys, json; print(json.load(sys.stdin)['result']['policy_encrypting_key'])"
