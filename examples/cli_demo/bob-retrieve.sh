#!/usr/bin/env bash

# Setup Bob prefabricated keyring
tar -xzvf ~/nucypher/examples/cli_demo/bob.tar.gz -C ~
mkdir --parents ~/bob/known_nodes/metadata
mkdir ~/bob/known_nodes/certificates

# Setup runtime environment
export NUCYPHER_KEYRING_PASSWORD=$TEST_BOB_KEYRING_PASSWORD
ALICE_KEY='03b9d29b7679dda13138b27d3f532d79369662f02b9a30246a0c839de7ae0d9d5e'
POLICY_KEY_1_1='0357ab01c0fec21fee5245a2388fbdefd0770a08ff4cfee6251588bea178549f0f'
TEACHER='discover.nucypher.network:9151'
RANDOM=$$
MESSAGE=$RANDOM

# Enrico does what he does best
nucypher enrico encrypt --policy-encrypting-key $POLICY_KEY_1_1 --message $MESSAGE --json-ipc | tee /tmp/enrico.json

MESSAGE_KIT=$(cat /tmp/enrico.json | python3 -c "import sys, json; print(json.load(sys.stdin)['result']['message_kit'])")

# Retrieve cleartext for message kit
nucypher bob retrieve \
    --label aceituno \
    --message-kit $MESSAGE_KIT \
    --policy-encrypting-key $POLICY_KEY_1_1 \
    --alice-verifying-key $ALICE_KEY \
    --teacher $TEACHER \
    --provider $INFURA_GOERLI_ENDPOINT \
    --config-file ~/bob/bob.json \
    --json-ipc \
    | tee /tmp/retrieve.json

# Test that the retrieved cleartext is correct
cat /tmp/retrieve.json \
| python3 -c "import sys, json, base64; assert b'$MESSAGE' == base64.b64decode(json.load(sys.stdin)['result']['cleartexts'][0])"
