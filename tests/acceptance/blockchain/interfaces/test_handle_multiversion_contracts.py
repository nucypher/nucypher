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


from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.sol.compile.constants import TEST_MULTIVERSION_CONTRACTS
from nucypher.blockchain.eth.sol.compile.types import SourceBundle
from nucypher.crypto.powers import TransactingPower
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD
from tests.utils.blockchain import free_gas_price_strategy

BlockchainDeployerInterface.GAS_STRATEGIES = {**BlockchainDeployerInterface.GAS_STRATEGIES,
                                              'free': free_gas_price_strategy}


def test_deployer_interface_multiversion_contract():

    # Prepare compiler
    base_dir = TEST_MULTIVERSION_CONTRACTS
    v1_dir, v2_dir = base_dir / 'v1', base_dir / 'v2'

    # TODO: Check type of sources
    # I am a contract administrator and I an compiling a new updated version of an existing contract...
    # Represents "Manually hardcoding" a new source directory on BlockchainDeployerInterface.SOURCES.
    BlockchainDeployerInterface.SOURCES = (
        SourceBundle(base_path=v1_dir),
        SourceBundle(base_path=v2_dir)
    )

    # Prepare chain
    BlockchainInterfaceFactory._interfaces.clear()
    blockchain_interface = BlockchainDeployerInterface(provider_uri='tester://pyevm', gas_strategy='free')
    blockchain_interface.connect()
    BlockchainInterfaceFactory.register_interface(interface=blockchain_interface)  # Lets this test run in isolation

    origin = blockchain_interface.client.accounts[0]
    blockchain_interface.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD, account=origin)
    blockchain_interface.transacting_power.activate()

    # Searching both contract through raw data
    contract_name = "VersionTest"
    requested_version = "v1.2.3"
    version, _data = blockchain_interface.find_raw_contract_data(contract_name=contract_name,
                                                                 requested_version=requested_version)
    assert version == requested_version
    version, _data = blockchain_interface.find_raw_contract_data(contract_name=contract_name,
                                                                 requested_version="latest")
    assert version == requested_version

    requested_version = "v1.1.4"
    version, _data = blockchain_interface.find_raw_contract_data(contract_name=contract_name,
                                                                 requested_version=requested_version)
    assert version == requested_version
    version, _data = blockchain_interface.find_raw_contract_data(contract_name=contract_name,
                                                                 requested_version="earliest")
    assert version == requested_version

    # Deploy different contracts and check their versions
    registry = InMemoryContractRegistry()
    contract, receipt = blockchain_interface.deploy_contract(deployer_address=origin,
                                                             registry=registry,
                                                             contract_name=contract_name,
                                                             contract_version="v1.1.4")
    assert contract.version == "v1.1.4"
    assert contract.functions.VERSION().call() == 1
    contract, receipt = blockchain_interface.deploy_contract(deployer_address=origin,
                                                             registry=registry,
                                                             contract_name=contract_name,
                                                             contract_version="earliest")
    assert contract.version == "v1.1.4"
    assert contract.functions.VERSION().call() == 1

    contract, receipt = blockchain_interface.deploy_contract(deployer_address=origin,
                                                             registry=registry,
                                                             contract_name=contract_name,
                                                             contract_version="v1.2.3")
    assert contract.version == "v1.2.3"
    assert contract.functions.VERSION().call() == 2
    contract, receipt = blockchain_interface.deploy_contract(deployer_address=origin,
                                                             registry=registry,
                                                             contract_name=contract_name,
                                                             contract_version="latest")
    assert contract.version == "v1.2.3"
    assert contract.functions.VERSION().call() == 2
    contract, receipt = blockchain_interface.deploy_contract(deployer_address=origin,
                                                             registry=registry,
                                                             contract_name=contract_name)
    assert contract.version == "v1.2.3"
    assert contract.functions.VERSION().call() == 2
