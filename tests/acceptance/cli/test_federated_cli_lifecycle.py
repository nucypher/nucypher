"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import json
from base64 import b64decode
from collections import namedtuple
from json import JSONDecodeError

import datetime
import maya
import os
import pytest
import pytest_twisted as pt
import shutil
from twisted.internet import threads
from web3 import Web3

from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import AliceConfiguration, BobConfiguration
from nucypher.config.constants import NUCYPHER_ENVVAR_KEYRING_PASSWORD, TEMPORARY_DOMAIN
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.utilities.logging import GlobalLoggerSettings
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD, TEST_PROVIDER_URI
from tests.utils.ursula import start_pytest_ursula_services, MOCK_KNOWN_URSULAS_CACHE

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
def test_federated_cli_lifecycle(click_runner,
                                 testerchain,
                                 random_policy_label,
                                 federated_ursulas,
                                 custom_filepath,
                                 custom_filepath_2):
    yield _cli_lifecycle(click_runner,
                         testerchain,
                         random_policy_label,
                         federated_ursulas,
                         custom_filepath,
                         custom_filepath_2)

    # for port in _ports_to_remove:
    #     del MOCK_KNOWN_URSULAS_CACHE[port]
    # MOCK_KNOWN_URSULAS_CACHE


@pt.inlineCallbacks
def test_decentralized_cli_lifecycle(click_runner,
                                     testerchain,
                                     random_policy_label,
                                     blockchain_ursulas,
                                     custom_filepath,
                                     custom_filepath_2,
                                     agency_local_registry):

    yield _cli_lifecycle(click_runner,
                         testerchain,
                         random_policy_label,
                         blockchain_ursulas,
                         custom_filepath,
                         custom_filepath_2,
                         agency_local_registry.filepath)



