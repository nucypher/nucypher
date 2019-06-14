import datetime
import json
import os
import shutil
from base64 import b64decode
from collections import namedtuple

import maya
import pytest
import pytest_twisted as pt
from twisted.internet import threads
from web3 import Web3

from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import AliceConfiguration, BobConfiguration
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD, TEMPORARY_DOMAIN, TEST_PROVIDER_URI
from nucypher.utilities.sandbox.ursula import start_pytest_ursula_services

PLAINTEXT = "I'm bereaved, not a sap!"


class MockSideChannel:

    PolicyAndLabel = namedtuple('PolicyAndLabel', ['encrypting_key', 'label'])
    BobPublicKeys = namedtuple('BobPublicKeys', ['bob_encrypting_key', 'bob_verifying_key'])

    class NoMessageKits(Exception):
        pass

    class NoPolicies(Exception):
        pass

    def __init__(self):
        self.__message_kits = []
        self.__policies = []
        self.__alice_public_keys = []
        self.__bob_public_keys = []

    def save_message_kit(self, message_kit: str) -> None:
        self.__message_kits.append(message_kit)

    def fetch_message_kit(self) -> UmbralMessageKit:
        if self.__message_kits:
            message_kit = self.__message_kits.pop()
            return message_kit
        raise self.NoMessageKits

    def save_policy(self, policy: PolicyAndLabel):
        self.__policies.append(policy)

    def fetch_policy(self) -> PolicyAndLabel:
        if self.__policies:
            policy = self.__policies[0]
            return policy
        raise self.NoPolicies

    def save_alice_pubkey(self, public_key):
        self.__alice_public_keys.append(public_key)

    def fetch_alice_pubkey(self):
        policy = self.__alice_public_keys.pop()
        return policy

    def save_bob_public_keys(self, public_keys: BobPublicKeys):
        self.__bob_public_keys.append(public_keys)

    def fetch_bob_public_keys(self) -> BobPublicKeys:
        policy = self.__bob_public_keys.pop()
        return policy


@pt.inlineCallbacks
@pytest.mark.parametrize('federated', (True, False))
def test_cli_lifecycle(click_runner,
                       random_policy_label,
                       federated_ursulas,
                       blockchain_ursulas,
                       custom_filepath,
                       custom_filepath_2,
                       federated):
    """
    This is an end to end integration test that runs each cli call
    in it's own process using only CLI character control entry points,
    and a mock side channel that runs in the control process
    """

    # Boring Setup Stuff
    alice_config_root = custom_filepath
    bob_config_root = custom_filepath_2
    envvars = {'NUCYPHER_KEYRING_PASSWORD': INSECURE_DEVELOPMENT_PASSWORD}

    # A side channel exists - Perhaps a dApp
    side_channel = MockSideChannel()

    shutil.rmtree(custom_filepath, ignore_errors=True)
    shutil.rmtree(custom_filepath_2, ignore_errors=True)

    """
    Scene 1: Alice Installs nucypher to a custom filepath and examines her configuration
    """

    # Alice performs an installation for the first time
    alice_init_args = ('alice', 'init',
                       '--network', TEMPORARY_DOMAIN,
                       '--config-root', alice_config_root)

    if federated:
        alice_init_args += ('--federated-only', )
    else:
        alice_init_args += ('--provider-uri', TEST_PROVIDER_URI)

    alice_init_response = click_runner.invoke(nucypher_cli, alice_init_args, catch_exceptions=False, env=envvars)
    assert alice_init_response.exit_code == 0

    # Alice uses her configuration file to run the character "view" command
    alice_configuration_file_location = os.path.join(alice_config_root, AliceConfiguration.generate_filename())
    alice_view_args = ('--json-ipc',
                       'alice', 'public-keys',
                       '--config-file', alice_configuration_file_location)

    alice_view_result = click_runner.invoke(nucypher_cli, alice_view_args, catch_exceptions=False, env=envvars)
    assert alice_view_result.exit_code == 0
    alice_view_response = json.loads(alice_view_result.output)

    # Alice expresses her desire to participate in data sharing with nucypher
    # by saving her public key somewhere Bob and Enrico can find it.
    side_channel.save_alice_pubkey(alice_view_response['result']['alice_verifying_key'])

    """
    Scene 2: Bob installs nucypher, examines his configuration and expresses his
    interest to participate in data retrieval by posting his public keys somewhere public (side-channel).
    """
    bob_init_args = ('bob', 'init',
                     '--network', TEMPORARY_DOMAIN,
                     '--config-root', bob_config_root)
    if federated:
        bob_init_args += ('--federated-only', )

    bob_init_response = click_runner.invoke(nucypher_cli, bob_init_args, catch_exceptions=False, env=envvars)
    assert bob_init_response.exit_code == 0

    # Alice uses her configuration file to run the character "view" command
    bob_configuration_file_location = os.path.join(bob_config_root, BobConfiguration.generate_filename())
    bob_view_args = ('--json-ipc',
                     'bob', 'public-keys',
                     '--config-file', bob_configuration_file_location)

    bob_view_result = click_runner.invoke(nucypher_cli, bob_view_args, catch_exceptions=False, env=envvars)
    assert bob_view_result.exit_code == 0
    bob_view_response = json.loads(bob_view_result.output)

    # Bob interacts with the sidechannel
    bob_public_keys = MockSideChannel.BobPublicKeys(bob_view_response['result']['bob_encrypting_key'],
                                                    bob_view_response['result']['bob_verifying_key'])

    side_channel.save_bob_public_keys(bob_public_keys)

    """
    Scene 3: Alice derives a policy keypair, and saves it's public key to a sidechannel.
    """

    random_label = random_policy_label.decode()  # Unicode string

    derive_args = ('--mock-networking',
                   '--json-ipc',
                   'alice', 'derive-policy-pubkey',
                   '--config-file', alice_configuration_file_location,
                   '--label', random_label)

    derive_response = click_runner.invoke(nucypher_cli, derive_args, catch_exceptions=False, env=envvars)
    assert derive_response.exit_code == 0

    derive_response = json.loads(derive_response.output)
    assert derive_response['result']['label'] == random_label

    # Alice and the sidechannel: at Tinagre
    policy = MockSideChannel.PolicyAndLabel(encrypting_key=derive_response['result']['policy_encrypting_key'],
                                            label=derive_response['result']['label'])
    side_channel.save_policy(policy=policy)

    """
    Scene 4: Enrico encrypts some data for some policy public key and saves it to a side channel.
    """
    def enrico_encrypts():

        # Fetch!
        policy = side_channel.fetch_policy()

        enrico_args = ('--json-ipc',
                       'enrico',
                       'encrypt',
                       '--policy-encrypting-key', policy.encrypting_key,
                       '--message', PLAINTEXT)

        encrypt_result = click_runner.invoke(nucypher_cli, enrico_args, catch_exceptions=False, env=envvars)
        assert encrypt_result.exit_code == 0

        encrypt_result = json.loads(encrypt_result.output)
        encrypted_message = encrypt_result['result']['message_kit']    # type: str

        side_channel.save_message_kit(message_kit=encrypted_message)
        return encrypt_result

    def _alice_decrypts(encrypt_result):
        """
        alice forgot what exactly she encrypted for bob.
        she decrypts it just to make sure.
        """
        policy = side_channel.fetch_policy()
        alice_signing_key = side_channel.fetch_alice_pubkey()
        message_kit = encrypt_result['result']['message_kit']

        decrypt_args = (
            '--mock-networking',
            '--json-ipc',
            'alice', 'decrypt',
            '--config-file', alice_configuration_file_location,
            '--message-kit', message_kit,
            '--label', policy.label,
        )

        if federated:
            decrypt_args += ('--federated-only',)

        decrypt_response_fail = click_runner.invoke(nucypher_cli, decrypt_args[0:7], catch_exceptions=False, env=envvars)
        assert decrypt_response_fail.exit_code == 2

        decrypt_response = click_runner.invoke(nucypher_cli, decrypt_args, catch_exceptions=False, env=envvars)
        decrypt_result = json.loads(decrypt_response.output)
        for cleartext in decrypt_result['result']['cleartexts']:
            assert b64decode(cleartext.encode()).decode() == PLAINTEXT

        # replenish the side channel
        side_channel.save_policy(policy=policy)
        side_channel.save_alice_pubkey(alice_signing_key)
        return encrypt_result

    """
    Scene 5: Alice grants access to Bob:
    We catch up with Alice later on, but before she has learned about existing Ursulas...
    """
    if federated:
        teacher = list(federated_ursulas)[0]
    else:
        teacher = list(blockchain_ursulas)[1]

    teacher_uri = teacher.seed_node_metadata(as_teacher_uri=True)

    # Some Ursula is running somewhere
    def _run_teacher(_encrypt_result):
        start_pytest_ursula_services(ursula=teacher)
        return teacher_uri

    def _grant(teacher_uri):

        # Alice fetched Bob's public keys from the side channel
        bob_keys = side_channel.fetch_bob_public_keys()
        bob_encrypting_key = bob_keys.bob_encrypting_key
        bob_verifying_key = bob_keys.bob_verifying_key

        grant_args = ('--mock-networking',
                      '--json-ipc',
                      'alice', 'grant',
                      '--network', TEMPORARY_DOMAIN,
                      '--teacher-uri', teacher_uri,
                      '--config-file', alice_configuration_file_location,
                      '--m', 2,
                      '--n', 3,
                      '--value', Web3.toWei(1, 'ether'),
                      '--expiration', (maya.now() + datetime.timedelta(days=3)).iso8601(),
                      '--label', random_label,
                      '--bob-encrypting-key', bob_encrypting_key,
                      '--bob-verifying-key', bob_verifying_key)

        if federated:
            grant_args += ('--federated-only',)
        else:
            grant_args += ('--provider-uri', TEST_PROVIDER_URI)

        grant_result = click_runner.invoke(nucypher_cli, grant_args, catch_exceptions=False, env=envvars)
        assert grant_result.exit_code == 0

        grant_result = json.loads(grant_result.output)

        # TODO: Expand test to consider manual treasure map handing
        # # Alice puts the Treasure Map somewhere Bob can get it.
        # side_channel.save_treasure_map(treasure_map=grant_result['result']['treasure_map'])

        return grant_result

    def _bob_retrieves(_grant_result):
        """
        Scene 6: Bob retrieves encrypted data from the side channel and uses nucypher to re-encrypt it
        """

        # Bob interacts with a sidechannel
        ciphertext_message_kit = side_channel.fetch_message_kit()

        policy = side_channel.fetch_policy()
        policy_encrypting_key, label = policy

        alice_signing_key = side_channel.fetch_alice_pubkey()

        retrieve_args = ('--mock-networking',
                         '--json-ipc',
                         'bob', 'retrieve',
                         '--teacher-uri', teacher_uri,
                         '--config-file', bob_configuration_file_location,
                         '--message-kit', ciphertext_message_kit,
                         '--label', label,
                         '--policy-encrypting-key', policy_encrypting_key,
                         '--alice-verifying-key', alice_signing_key)

        if federated:
            retrieve_args += ('--federated-only',)

        retrieve_response = click_runner.invoke(nucypher_cli, retrieve_args, catch_exceptions=False, env=envvars)
        assert retrieve_response.exit_code == 0

        retrieve_response = json.loads(retrieve_response.output)
        for cleartext in retrieve_response['result']['cleartexts']:
            assert b64decode(cleartext.encode()).decode() == PLAINTEXT

        return

    # Run the Callbacks
    d = threads.deferToThread(enrico_encrypts)  # scene 4
    d.addCallback(_alice_decrypts)              # scene 5 (uncertainty)
    d.addCallback(_run_teacher)                 # scene 6 (preamble)
    d.addCallback(_grant)                       # scene 7
    d.addCallback(_bob_retrieves)               # scene 8

    yield d
