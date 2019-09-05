#!/usr/bin/env python

import base64
import json
import os

import click

from nucypher.cli.config import nucypher_click_config
from nucypher.characters.lawful import Enrico
from nucypher.cli.actions import make_cli_character
from nucypher.config.characters import AliceConfiguration
from nucypher.crypto.powers import SigningPower


@click.command()
@click.option('--plaintext-dir', type=click.STRING, required=True)
@click.option('--outfile', type=click.STRING)
@click.option('--alice-config', type=click.STRING)
@click.option('--label', type=click.STRING, required=True)
@nucypher_click_config
def mario_box_cli(click_config, plaintext_dir, alice_config, label, outfile):

    # Derive Policy Encrypting Key
    alice_configuration = AliceConfiguration.from_configuration_file(filepath=alice_config)
    alice = make_cli_character(character_config=alice_configuration, click_config=click_config)
    alice_signing_key = alice.public_keys(SigningPower)
    policy_encrypting_key = alice.get_policy_encrypting_key_from_label(label=label.encode())
    policy_encrypting_key_hex = bytes(policy_encrypting_key).hex()

    output = list()
    paths = list(os.listdir(plaintext_dir))
    click.secho(f"Encrypting {len(paths)} files for policy {policy_encrypting_key_hex}", fg='blue')

    with click.progressbar(paths) as bar:
        for path in bar:
            filepath = os.path.join(plaintext_dir, path)
            with open(filepath, 'rb') as file:
                plaintext = file.read()
                encoded_plaintext = base64.b64encode(plaintext)

                enrico = Enrico(policy_encrypting_key=policy_encrypting_key)
                message_kit, _signature = enrico.encrypt_message(message=encoded_plaintext)
                base64_message_kit = base64.b64encode(message_kit.to_bytes()).decode()

                # Collect Bob Retrieve JSON Requests
                retrieve_payload = {'label': label,
                                    'policy-encrypting-key': policy_encrypting_key_hex,
                                    'alice-verifying-key': bytes(alice_signing_key).hex(),
                                    'message-kit': base64_message_kit}

                output.append(retrieve_payload)

    if not outfile:
        outfile = f'{policy_encrypting_key_hex}.json'

    with open(outfile, 'w') as file:
        file.write(json.dumps(output, indent=2))
    click.secho(f"Successfully wrote output to {outfile}", fg='green')


if __name__ == '__main__':
    mario_box_cli()
