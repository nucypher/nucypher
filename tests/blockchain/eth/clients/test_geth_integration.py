import os

import pytest
from eth_utils import to_checksum_address

from nucypher.blockchain.eth.actors import Deployer
from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.interfaces import BlockchainInterface, BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import InMemoryEthereumContractRegistry
from nucypher.crypto.api import verify_eip_191


#
# NOTE: This module is skipped on CI
#
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD


def test_geth_EIP_191_client_signature_integration(geth_dev_node):
    if 'CIRCLECI' in os.environ:
        pytest.skip("Do not run Geth nodes in CI")

    # Start a geth process
    blockchain = BlockchainInterface(provider_process=geth_dev_node, sync_now=False)
    blockchain.connect(fetch_registry=False, sync_now=False)

    # Sign a message (RPC) and verify it.
    etherbase = blockchain.client.accounts[0]
    stamp = b'STAMP-' + os.urandom(64)
    signature = blockchain.client.sign_message(account=etherbase, message=stamp)
    is_valid = verify_eip_191(address=etherbase,
                              signature=signature,
                              message=stamp)
    assert is_valid


def test_geth_deploy(geth_dev_node):
    if 'CIRCLECI' in os.environ:
        pytest.skip("Do not run Geth nodes in CI")

    # Start a geth process
    memory_registry = InMemoryEthereumContractRegistry()
    blockchain = BlockchainDeployerInterface(provider_process=geth_dev_node,
                                             fetch_registry=False,
                                             registry=memory_registry,
                                             sync_now=False)

    # Make Deployer
    etherbase = to_checksum_address(geth_dev_node.accounts[0].decode())
    deployer = Deployer(blockchain=blockchain,
                        deployer_address=etherbase,
                        client_password=INSECURE_DEVELOPMENT_PASSWORD)

    assert int(deployer.blockchain.client.chain_id) == 1337

    # Deploy
    deployer.deploy_network_contracts(staker_secret=INSECURE_DEVELOPMENT_PASSWORD,
                                      policy_secret=INSECURE_DEVELOPMENT_PASSWORD,
                                      adjudicator_secret=INSECURE_DEVELOPMENT_PASSWORD,
                                      user_escrow_proxy_secret=INSECURE_DEVELOPMENT_PASSWORD)

    # TODO: Confirm Successful Deployment
