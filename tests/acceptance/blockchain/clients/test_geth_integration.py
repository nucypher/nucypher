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

import os

import pytest
from eth_utils import is_checksum_address, to_checksum_address

from nucypher.blockchain.eth.actors import ContractAdministrator
from nucypher.blockchain.eth.interfaces import (
    BlockchainDeployerInterface,
    BlockchainInterface,
    BlockchainInterfaceFactory
)
from nucypher.crypto.api import verify_eip_191
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD
from tests.markers import skip_on_circleci


@pytest.mark.skip()
@skip_on_circleci
def test_geth_EIP_191_client_signature_integration(instant_geth_dev_node):

    # Start a geth process
    instant_geth_dev_node.start()

    blockchain = BlockchainInterface(provider_uri=instant_geth_dev_node.provider_uri())
    blockchain.connect()

    # Sign a message (RPC) and verify it.
    etherbase = blockchain.client.accounts[0]
    stamp = b'STAMP-' + os.urandom(64)
    signature = blockchain.client.sign_message(account=etherbase, message=stamp)
    is_valid = verify_eip_191(address=etherbase,
                              signature=signature,
                              message=stamp)
    assert is_valid


@pytest.mark.skip()
@skip_on_circleci
def test_geth_create_new_account(instant_geth_dev_node):
    blockchain = BlockchainInterface(provider_uri=instant_geth_dev_node.provider_uri())
    blockchain.connect()
    new_account = blockchain.client.new_account(password=INSECURE_DEVELOPMENT_PASSWORD)
    assert is_checksum_address(new_account)
