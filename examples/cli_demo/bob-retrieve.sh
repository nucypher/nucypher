#!/usr/bin/env bash

# Setup Bob prefabricated keyring
tar -xzf ~/nucypher/examples/cli_demo/bob.tar.gz -C ~
mkdir --parents ~/bob/known_nodes/metadata
mkdir ~/bob/known_nodes/certificates
mkdir --parents /tmp/cli-demo

# Setup runtime environment
export NUCYPHER_KEYRING_PASSWORD=$TEST_BOB_KEYRING_PASSWORD
ALICE_KEY='03b9d29b7679dda13138b27d3f532d79369662f02b9a30246a0c839de7ae0d9d5e'

TEACHER='discover.nucypher.network:9151'
RANDOM=$$
MESSAGE=$RANDOM

if [ -f /tmp/grant.json ]; then
    PARSE_POLICY_KEY=$(cat /tmp/grant.json \
        | python3 -c "import sys, json; print(json.load(sys.stdin)['result']['policy_encrypting_key'])")
    POLICY_KEY="${PARSE_POLICY_KEY}"
    LABEL=$1
else
    # Use a predefined label and policy encrypting key
    LABEL=aceituno
    POLICY_KEY='0357ab01c0fec21fee5245a2388fbdefd0770a08ff4cfee6251588bea178549f0f'
fi

# Enrico does what he does best
nucypher enrico encrypt --policy-encrypting-key $POLICY_KEY --message $MESSAGE --json-ipc | tee /tmp/enrico.json

cp /tmp/enrico.json /tmp/cli-demo
cp ~/.cache/nucypher/log/nucypher.log /tmp/cli-demo

MESSAGE_KIT=$(cat /tmp/enrico.json | python3 -c "import sys, json; print(json.load(sys.stdin)['result']['message_kit'])")

# Bob retrieves cleartext for message kit
nucypher bob retrieve \
    --label $LABEL \
    --message-kit $MESSAGE_KIT \
    --policy-encrypting-key $POLICY_KEY \
    --alice-verifying-key $ALICE_KEY \
    --teacher $TEACHER \
    --provider $INFURA_GOERLI_ENDPOINT \
    --config-file ~/bob/bob.json \
    --json-ipc \
    | tee /tmp/retrieve.json

cp /tmp/retrieve.json /tmp/cli-demo
cp ~/.cache/nucypher/log/nucypher.log /tmp/cli-demo

# Test that the retrieved cleartext is correct
cat /tmp/retrieve.json \
| python3 -c "import sys, json, base64; assert b'$MESSAGE' == base64.b64decode(json.load(sys.stdin)['result']['cleartexts'][0])"
