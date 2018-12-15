"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import os

from twisted.logger import Logger

from constant_sorrow.constants import NO_BLOCKCHAIN_AVAILABLE
from typing import List, Tuple

from nucypher.blockchain.eth.actors import Deployer
from nucypher.blockchain.eth.agents import NucypherTokenAgent, MinerAgent, PolicyAgent
from nucypher.blockchain.eth.constants import DISPATCHER_SECRET_LENGTH
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import InMemoryEthereumContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.config.constants import CONTRACT_ROOT
from umbral.keys import UmbralPrivateKey
from web3.middleware import geth_poa_middleware

from nucypher.blockchain.eth import constants
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.utilities.sandbox.constants import (DEVELOPMENT_ETH_AIRDROP_AMOUNT,
                                                  NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK,
                                                  INSECURE_DEVELOPMENT_PASSWORD)


def token_airdrop(token_agent, amount: int, origin: str, addresses: List[str]):
    """Airdrops tokens from creator address to all other addresses!"""

    def txs():
        for address in addresses:
            txhash = token_agent.contract.functions.transfer(address, amount).transact({'from': origin})
            yield txhash

    receipts = list()
    for tx in txs():  # One at a time
        receipt = token_agent.blockchain.wait_for_receipt(tx)
        receipts.append(receipt)
    return receipts


class TesterBlockchain(Blockchain):
    """
    Blockchain subclass with additional test utility methods and options.
    """

    _PROVIDER_URI = 'tester://pyevm'
    _instance = NO_BLOCKCHAIN_AVAILABLE
    _test_account_cache = list()
    _default_test_accounts = 10

    def __init__(self, test_accounts=_default_test_accounts, poa=True, airdrop=True, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.log = Logger("test-blockchain")  # type: Logger

        # For use with Proof-Of-Authority test-blockchains
        if poa is True:
            w3 = self.interface.w3
            w3.middleware_stack.inject(geth_poa_middleware, layer=0)

        # Generate additional ethereum accounts for testing
        enough_accounts = len(self.interface.w3.eth.accounts) >= NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK
        if test_accounts is not None and not enough_accounts:

            accounts_to_make = NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK - len(self.interface.w3.eth.accounts)
            test_accounts = test_accounts if test_accounts is not None else NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK

            self.__generate_insecure_unlocked_accounts(quantity=accounts_to_make)

            assert test_accounts == len(self.interface.w3.eth.accounts)

        if airdrop is True:  # ETH for everyone!
            self.ether_airdrop(amount=DEVELOPMENT_ETH_AIRDROP_AMOUNT)

    @classmethod
    def sever_connection(cls) -> None:
        cls._instance = NO_BLOCKCHAIN_AVAILABLE

    def __generate_insecure_unlocked_accounts(self, quantity: int) -> List[str]:
        """
        Generate additional unlocked accounts transferring a balance to each account on creation.
        """
        addresses = list()
        insecure_password = INSECURE_DEVELOPMENT_PASSWORD
        for _ in range(quantity):

            umbral_priv_key = UmbralPrivateKey.gen_key()
            address = self.interface.w3.personal.importRawKey(private_key=umbral_priv_key.to_bytes(),
                                                              passphrase=insecure_password)

            assert self.interface.unlock_account(address, password=insecure_password), 'Failed to unlock {}'.format(address)
            addresses.append(address)
            self._test_account_cache.append(address)
            self.log.info('Generated new insecure account {}'.format(address))

        return addresses

    def ether_airdrop(self, amount: int) -> List[str]:
        """Airdrops ether from creator address to all other addresses!"""

        coinbase, *addresses = self.interface.w3.eth.accounts

        tx_hashes = list()
        for address in addresses:

            tx = {'to': address, 'from': coinbase, 'value': amount}
            txhash = self.interface.w3.eth.sendTransaction(tx)

            _receipt = self.wait_for_receipt(txhash)
            tx_hashes.append(txhash)
            self.log.info("Airdropped {} ETH {} -> {}".format(amount, tx['from'], tx['to']))

        return tx_hashes

    def time_travel(self, hours: int=None, seconds: int=None, periods: int=None):
        """
        Wait the specified number of wait_hours by comparing
        block timestamps and mines a single block.
        """

        more_than_one_arg = sum(map(bool, (hours, seconds, periods))) > 1
        if more_than_one_arg:
            raise ValueError("Specify hours, seconds, or lock_periods, not a combination")

        if periods:
            duration = (constants.HOURS_PER_PERIOD * periods) * (60*60)
            base = constants.HOURS_PER_PERIOD * 60 * 60
        elif hours:
            duration = hours * (60*60)
            base = 60 * 60
        elif seconds:
            duration = seconds
            base = 1
        else:
            raise ValueError("Specify either hours, seconds, or lock_periods.")

        now = self.interface.w3.eth.getBlock(block_identifier='latest').timestamp
        end_timestamp = ((now+duration)//base) * base

        self.interface.w3.eth.web3.testing.timeTravel(timestamp=end_timestamp)
        self.interface.w3.eth.web3.testing.mine(1)
        self.log.info("Time traveled to {}".format(end_timestamp))

    @classmethod
    def connect(cls, *args, **kwargs) -> 'TesterBlockchain':
        solidity_compiler = SolidityCompiler(test_contract_dir=CONTRACT_ROOT)
        memory_registry = InMemoryEthereumContractRegistry()
        interface = BlockchainDeployerInterface(provider_uri=cls._PROVIDER_URI, compiler=solidity_compiler, registry=memory_registry)
        testerchain = TesterBlockchain(interface=interface, test_accounts=cls._default_test_accounts, airdrop=False)
        return testerchain

    @classmethod
    def bootstrap_network(cls) -> Tuple['TesterBlockchain', List[str]]:

        def __deploy_contracts(testerchain: TesterBlockchain) -> None:
            origin = testerchain.interface.w3.eth.accounts[0]
            deployer = Deployer(blockchain=testerchain, deployer_address=origin, bare=True)
            _txhashes, _agents = deployer.deploy_network_contracts(miner_secret=os.urandom(DISPATCHER_SECRET_LENGTH),
                                                                   policy_secret=os.urandom(DISPATCHER_SECRET_LENGTH))

        testerchain = cls.connect()
        __deploy_contracts(testerchain=testerchain)
        return testerchain, testerchain.interface.w3.eth.accounts
