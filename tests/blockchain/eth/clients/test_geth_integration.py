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
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterface, \
    BlockchainInterfaceFactory
from nucypher.crypto.api import verify_eip_191
#
# NOTE: This module is skipped on CI
#
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD


def test_geth_EIP_191_client_signature_integration(instant_geth_dev_node):

    # TODO: #1909 Move to decorator
    if 'CIRCLECI' in os.environ:
        pytest.skip("Do not run Geth nodes in CI")

    # Start a geth process
    blockchain = BlockchainInterface(provider_process=instant_geth_dev_node, poa=True)
    blockchain.connect()

    # Sign a message (RPC) and verify it.
    etherbase = blockchain.client.accounts[0]
    stamp = b'STAMP-' + os.urandom(64)
    signature = blockchain.client.sign_message(account=etherbase, message=stamp)
    is_valid = verify_eip_191(address=etherbase,
                              signature=signature,
                              message=stamp)
    assert is_valid


def test_geth_create_new_account(instant_geth_dev_node):

    # TODO: #1909 Move to decorator
    if 'CIRCLECI' in os.environ:
        pytest.skip("Do not run Geth nodes in CI")

    blockchain = BlockchainInterface(provider_process=instant_geth_dev_node, poa=True)
    blockchain.connect()
    new_account = blockchain.client.new_account(password=INSECURE_DEVELOPMENT_PASSWORD)
    assert is_checksum_address(new_account)


@pytest.mark.skip(reason="See Issue #1955")
def test_geth_deployment_integration(instant_geth_dev_node, test_registry):

    # TODO: #1909 Move to decorator
    if 'CIRCLECI' in os.environ:
        pytest.skip("Do not run Geth nodes in CI")

    blockchain = BlockchainDeployerInterface(provider_process=instant_geth_dev_node, poa=True)  # always poa here.
    BlockchainInterfaceFactory.register_interface(interface=blockchain)

    # Make Deployer
    etherbase = to_checksum_address(instant_geth_dev_node.accounts[0].decode())  # TODO: Make property on nucypher geth node instances?
    administrator = ContractAdministrator(registry=test_registry,
                                          deployer_address=etherbase,
                                          client_password=None)  # dev accounts have no password.

    assert int(blockchain.client.chain_id) == 1337

    # Deploy
    administrator.deploy_network_contracts(interactive=False)  # just do it
