from collections import Counter

from eth_utils import ValidationError
from pathlib import Path

from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.sol.compile import ALLOWED_PATHS
from nucypher.crypto.powers import TransactingPower
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD


def test_multiversion_contract(mocker):

    # Prepare compiler
    base_dir = Path(__file__).parent / 'contracts' / 'multiversion'
    v1_dir, v2_dir = base_dir / 'v1', base_dir / 'v2'

    # I am a contract administrator and I an compiling a new updated version of an existing contract...
    # Represents "Manually hardcoding" a new permitted compile path in compile.py
    # and new source directory on BlockchainDeployerInterface.SOURCES.
    ALLOWED_PATHS.append(base_dir)
    BlockchainDeployerInterface.SOURCES = (v1_dir, v2_dir)

    # Prepare chain
    BlockchainInterfaceFactory._interfaces.clear()
    blockchain_interface = BlockchainDeployerInterface(provider_uri='tester://pyevm')
    blockchain_interface.connect()
    BlockchainInterfaceFactory.register_interface(interface=blockchain_interface)  # Lets this test run in isolation

    origin = blockchain_interface.client.accounts[0]
    blockchain_interface.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD, account=origin)
    blockchain_interface.transacting_power.activate()

    nonce_spy = mocker.spy(BlockchainDeployerInterface, 'sign_and_broadcast_transaction')
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
