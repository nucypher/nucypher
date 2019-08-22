#!/usr/bin/env python

import base64
import json
import os

import click
import libnacl.secret

from nucypher.characters.lawful import Enrico
from nucypher.cli.actions import make_cli_character
from nucypher.config.characters import AliceConfiguration


@click.command()
# @click.option('--plaintext-pass-through', type=click.BOOL, required=True)  # FIXME
@click.option('--plaintext-dir', type=click.STRING, required=True)
@click.option('--alice-config', type=click.STRING)
@click.option('--label', type=click.STRING, required=True)
def mario_box_cli(plaintext_dir, alice_config, label):
    click.secho("Starting Up...", fg='green')

    # Derive Policy Encrypting Key
    alice_configuration = AliceConfiguration.from_configuration_file(filepath=alice_config)
    alice = make_cli_character(character_config=alice_configuration)
    policy_encrypting_key = alice.get_policy_encrypting_key_from_label(label=label.encode())

    message_kits = list()
    paths = list(os.listdir(plaintext_dir))
    for path in paths:
        filepath = os.path.join(plaintext_dir, path)
        click.secho(f'Processing {filepath}...')
        with open(filepath, 'rb') as file:
            plaintext = file.read()
            encoded_plaintext = base64.b64encode(plaintext)

            # Make the Box
            box = libnacl.secret.SecretBox()

            # Encrypt file contents symmetrically
            ciphertext = box.encrypt(encoded_plaintext)
            base64_ciphertext = base64.b64encode(ciphertext).decode()

            # Encrypt the symmetric key
            enrico = Enrico(policy_encrypting_key=policy_encrypting_key)
            message_kit, _signature = enrico.encrypt_message(message=box.sk)
            base64_message_kit = base64.b64encode(bytes(message_kit)).decode()

            # Collect ciphertext-message-kit pairs.
            message_kits.append((base64_ciphertext, base64_message_kit))
            click.secho(f"Encrypted {filepath}...")

    # Generate the output
    output = {'ciphertexts': message_kits, 'pek': bytes(policy_encrypting_key).hex()}
    click.secho(json.dumps(output))


if __name__ == '__main__':
    mario_box_cli()
