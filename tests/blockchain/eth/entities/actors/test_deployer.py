import os

from nucypher.blockchain.eth.actors import Deployer
from nucypher.blockchain.eth.registry import InMemoryEthereumContractRegistry


def test_rapid_deployment():
    memory_registry = InMemoryEthereumContractRegistry()
    deployer = Deployer.from_blockchain(provider_uri='tester://pyevm',
                                        registry=memory_registry,

                                        )

    deployer_address, *all_yall = deployer.blockchain.interface.w3.eth.accounts
    deployer.deployer_address = deployer_address

    deployer.deploy_network_contracts(miner_secret=os.urandom(32),
                                      policy_secret=os.urandom(32))

    deployer.deploy_escrow_proxy(secret=os.urandom(32))
    data = [{'address': all_yall[1], 'amount': 100, 'periods': 100},
            {'address': all_yall[2], 'amount': 133432, 'periods': 1},
            {'address': all_yall[3], 'amount': 999, 'periods': 30}]
    deployer.deploy_beneficiary_contracts(allocations=data)

