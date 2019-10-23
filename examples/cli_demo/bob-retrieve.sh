#!/usr/bin/env bash

# Setup Bob prefabricated keyring
tar -xzvf ~/nucypher/examples/cli_demo/bob.tar.gz -C ~
mkdir --parents ~/bob/known_nodes/metadata
mkdir ~/bob/known_nodes/certificates

# Setup runtime environment
export NUCYPHER_KEYRING_PASSWORD=$TEST_BOB_KEYRING_PASSWORD
ALICE_KEY='03b9d29b7679dda13138b27d3f532d79369662f02b9a30246a0c839de7ae0d9d5e'
MESSAGE_KIT_1_1='AlooTwfXivMR7rS/7aIECXS7AHMUErGRPUocWmJiajI+AjzuSuGfsCrbwR7rpyYDDALEjbFsCGtthPFy7htMn3pN6sSvAkmFPvATL1tkBBBhMNgXpxPma6i3FBgLo6cCWzcCJSHHNymL6VuuvTTkQAagsEUh7wj5YfURNR4J7cEqsL1yFjsPUsYqLGegD4D9uYjBf7uNrBiu0le4q0A/wTfqIgtHI1RsNPhqCnBYUkb/6UxGT55Bz+8Ndk106ZRQxRzRyIMsFQvpau3foBhYfZrQ3FSKNzVpJKuwP6Nw4xQV/vs+ObSkJci0vHjQbT4VmcI+zztM4lQ7Sx+bF/AUUEjIb/R0xVjZoaawwaXk5wlGV3A='
POLICY_KEY_1_1='0357ab01c0fec21fee5245a2388fbdefd0770a08ff4cfee6251588bea178549f0f'
TEACHER='discover.nucypher.network:9151'

# Retrieve cleartext for message kit
nucypher bob retrieve --label aceituno --message-kit $MESSAGE_KIT_1_1 --policy-encrypting-key $POLICY_KEY_1_1 --alice-verifying-key $ALICE_KEY --teacher $TEACHER --debug --config-file ~/bob/bob.json --provider $INFURA_GOERLI_ENDPOINT > retrieve-output.txt
cat retrieve-output.txt

# Test that retrieved cleartext is correct
EXPECTED_OUTPUT="cleartexts ...... ['QWNlaXR1bm8gZXMgZWwgcGVycm8gbcOhcyBwZXJydW5v']"
diff <(tail -1 retrieve-output.txt) <(echo $EXPECTED_OUTPUT)