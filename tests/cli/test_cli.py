import os

import pytest_twisted as pt
from twisted.internet import threads

from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import AliceConfiguration
from nucypher.crypto.powers import DecryptingPower, SigningPower
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD, TEMPORARY_DOMAIN
from nucypher.utilities.sandbox.ursula import start_pytest_ursula_services


@pt.inlineCallbacks
def test_cli_lifecycle(click_runner,
                       random_policy_label,
                       federated_bob,
                       federated_alice,
                       federated_ursulas,
                       custom_filepath):

    envvars = {'NUCYPHER_KEYRING_PASSWORD': INSECURE_DEVELOPMENT_PASSWORD}

    #
    # Initialize Alice
    #
    init_args = ('alice', 'init',
                 '--federated-only',
                 '--network', TEMPORARY_DOMAIN,
                 '--config-root', custom_filepath)

    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    #
    # Alice Derives a Policy
    #
    custom_config_file = os.path.join(custom_filepath, AliceConfiguration.CONFIG_FILENAME)
    random_label = random_policy_label.decode()  # Unicode string
    derive_args = ('alice', 'derive-policy',
                   '--config-file', custom_config_file,
                   '--label', random_label)

    result = click_runner.invoke(nucypher_cli, derive_args,
                                 catch_exceptions=False, env=envvars)

    assert random_label in result.output

    #
    # Alice Grants
    #

    teacher = list(federated_ursulas)[1]
    start_pytest_ursula_services(ursula=teacher)

    # "Remember" Ursula
    # alice_known_nodes_dir = os.path.join(custom_filepath, 'known_nodes', 'metadata')
    # filename = f'{teacher.checksum_public_address}.node'
    # with open(os.path.join(alice_known_nodes_dir, filename), 'wb') as f:
    #     f.write(NodeStorage.NODE_SERIALIZER(bytes(teacher)))

    def _grant():
        bob_encrypting_key_hex = bytes(federated_bob.public_keys(DecryptingPower)).hex()
        bob_signing_key_hex = bytes(federated_bob.public_keys(SigningPower)).hex()

        grant_args = ('alice', 'grant',
                      '--teacher-uri', teacher.rest_interface,
                      '--config-file', custom_config_file,
                      '--m', 1,
                      '--n', 1,
                      '--label', random_label,
                      '--bob-encrypting-key', bob_encrypting_key_hex,
                      '--bob-verifying-key', bob_signing_key_hex)

        grant_result = click_runner.invoke(nucypher_cli, grant_args, catch_exceptions=False, env=envvars)

        assert False

    d = threads.deferToThread(_grant)
    yield d

    # policy_pubkey_enc_hex = alice_response_data['result']['policy_encrypting_key']
    # alice_pubkey_sig_hex = alice_response_data['result']['alice_signing_key']
    # label = alice_response_data['result']['label']
    #
    # enrico_encoded_message = "I'm bereaved, not a sap!"  # type: str
    # enrico_request_data = {
    #     'message': enrico_encoded_message,
    # }
    #
    # response = enrico_control_from_alice.post('/encrypt_message', data=json.dumps(enrico_request_data))
    #
    # enrico_response_data = json.loads(response.data)
    #
    # kit_bytes = b64decode(enrico_response_data['result']['message_kit'].encode())
    # bob_message_kit = UmbralMessageKit.from_bytes(kit_bytes)
    #
    # # Retrieve data via Bob control
    # encoded_message_kit = b64encode(bob_message_kit.to_bytes()).decode()
    #
    # # Give bob a node to remember
    # teacher = list(federated_ursulas)[1]
    # federated_bob.remember_node(teacher)
    #
    # response = bob_control_test_client.post('/retrieve', data=json.dumps(bob_request_data))
    #
    # bob_response_data = json.loads(response.data)
    #
    # for plaintext in bob_response_data['result']['plaintext']:
    #     plaintext_bytes = b64decode(plaintext)
    assert False
