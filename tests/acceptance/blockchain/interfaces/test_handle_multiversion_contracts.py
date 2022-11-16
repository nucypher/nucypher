


from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.signers.software import Web3Signer
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
    blockchain_interface = BlockchainDeployerInterface(eth_provider_uri='tester://pyevm', gas_strategy='free')
    blockchain_interface.connect()
    BlockchainInterfaceFactory.register_interface(interface=blockchain_interface)  # Lets this test run in isolation

    origin = blockchain_interface.client.accounts[0]
    transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                         signer=Web3Signer(blockchain_interface.client),
                                         account=origin)

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
    contract, receipt = blockchain_interface.deploy_contract(transacting_power=transacting_power,
                                                             registry=registry,
                                                             contract_name=contract_name,
                                                             contract_version="v1.1.4")
    assert contract.version == "v1.1.4"
    assert contract.functions.VERSION().call() == 1
    contract, receipt = blockchain_interface.deploy_contract(transacting_power=transacting_power,
                                                             registry=registry,
                                                             contract_name=contract_name,
                                                             contract_version="earliest")
    assert contract.version == "v1.1.4"
    assert contract.functions.VERSION().call() == 1

    contract, receipt = blockchain_interface.deploy_contract(transacting_power=transacting_power,
                                                             registry=registry,
                                                             contract_name=contract_name,
                                                             contract_version="v1.2.3")
    assert contract.version == "v1.2.3"
    assert contract.functions.VERSION().call() == 2
    contract, receipt = blockchain_interface.deploy_contract(transacting_power=transacting_power,
                                                             registry=registry,
                                                             contract_name=contract_name,
                                                             contract_version="latest")
    assert contract.version == "v1.2.3"
    assert contract.functions.VERSION().call() == 2
    contract, receipt = blockchain_interface.deploy_contract(transacting_power=transacting_power,
                                                             registry=registry,
                                                             contract_name=contract_name)
    assert contract.version == "v1.2.3"
    assert contract.functions.VERSION().call() == 2
