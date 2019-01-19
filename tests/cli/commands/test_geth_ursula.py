from nucypher.cli.processes import UrsulaGethDevProcess
import os
import random
import string

from web3.auto import w3

from nucypher.blockchain.eth.actors import Deployer
from nucypher.blockchain.eth.constants import MIN_LOCKED_PERIODS, MIN_ALLOWED_LOCKED, MAX_MINTING_PERIODS, \
    MAX_ALLOWED_LOCKED, ONE_YEAR_IN_SECONDS
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import InMemoryEthereumContractRegistry, InMemoryAllocationRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.cli.processes import UrsulaGethDevProcess
from nucypher.config.characters import UrsulaConfiguration
from nucypher.utilities.sandbox.blockchain import TesterBlockchain
from nucypher.utilities.sandbox.constants import MOCK_URSULA_STARTING_PORT
from nucypher.utilities.sandbox.middleware import MockRestMiddleware


def test_run_geth_development_ursula():

    #
    # Geth
    #
    # geth = UrsulaGethDevProcess(chain_name="tester")
    # geth.start()
    # geth.wait_for_ipc(timeout=30)  # wait up to 30 seconds for the IPC socket to open

    #
    # Interface
    #
    compiler = SolidityCompiler()
    registry = InMemoryEthereumContractRegistry()
    allocation_registry = InMemoryAllocationRegistry()
    interface = BlockchainDeployerInterface(compiler=compiler,
                                            registry=registry,
                                            provider_uri=f"ipc:///tmp/geth.ipc")

    #
    # Blockchain
    #
    blockchain = TesterBlockchain(interface=interface, airdrop=False, poa=True)
    blockchain.ether_airdrop(amount=1000000000)
    origin, *everyone = blockchain.interface.w3.eth.accounts

    #
    # Delpoyer
    #
    deployer = Deployer(blockchain=blockchain,
                        allocation_registry=allocation_registry,
                        deployer_address=origin)

    deployer_address, *all_yall = deployer.blockchain.interface.w3.eth.accounts

    # The Big Three (+ Dispatchers)
    deployer.deploy_network_contracts(miner_secret=os.urandom(32),
                                      policy_secret=os.urandom(32))

    # User Escrow Proxy
    deployer.deploy_escrow_proxy(secret=os.urandom(32))

    # Start with some hard-coded cases...
    allocation_data = [{'address': all_yall[1], 'amount': MAX_ALLOWED_LOCKED, 'duration': ONE_YEAR_IN_SECONDS}]

    deployer.deploy_beneficiary_contracts(allocations=allocation_data)


    #
    # Ursula
    #
    ursula_config = UrsulaConfiguration(dev_mode=True,
                                        is_me=True,
                                        checksum_public_address='0xeA72FF7e9467fd0Bbc52690CbfEaCc0F6F1c2a68',
                                        provider_uri=f"ipc:///tmp/geth.ipc",
                                        poa=True,
                                        rest_port=MOCK_URSULA_STARTING_PORT,
                                        start_learning_now=False,
                                        abort_on_learning_error=True,
                                        federated_only=False,
                                        network_middleware=MockRestMiddleware(),
                                        import_seed_registry=False,
                                        save_metadata=False,
                                        reload_metadata=False)

    ursula = ursula_config()
    assert False
