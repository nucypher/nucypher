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
from typing import List, Tuple, Dict

import maya
from constant_sorrow.constants import NO_BLOCKCHAIN_AVAILABLE, TEST_PROVIDER_ON_MAIN_PROCESS
from twisted.logger import Logger
from web3 import Web3
from web3.middleware import geth_poa_middleware

from nucypher.blockchain.economics import TokenEconomics
from nucypher.blockchain.eth.actors import Deployer
from nucypher.blockchain.eth.agents import EthereumContractAgent
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import InMemoryEthereumContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.blockchain.eth.token import NU
from nucypher.blockchain.eth.utils import epoch_to_period
from nucypher.config.constants import CONTRACT_ROOT
from nucypher.utilities.sandbox.constants import (
    NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS,
    NUMBER_OF_ETH_TEST_ACCOUNTS,
    DEVELOPMENT_ETH_AIRDROP_AMOUNT,
    STAKING_ESCROW_DEPLOYMENT_SECRET,
    POLICY_MANAGER_DEPLOYMENT_SECRET,
    ADJUDICATOR_DEPLOYMENT_SECRET,
    USER_ESCROW_PROXY_DEPLOYMENT_SECRET
)


def token_airdrop(token_agent, amount: NU, origin: str, addresses: List[str]):
    """Airdrops tokens from creator address to all other addresses!"""

    def txs():
        args = {'from': origin, 'gasPrice': token_agent.blockchain.interface.w3.eth.gasPrice}
        for address in addresses:
            txhash = token_agent.contract.functions.transfer(address, int(amount)).transact(args)
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

    _default_test_accounts = NUMBER_OF_ETH_TEST_ACCOUNTS

    # Reserved addresses
    _ETHERBASE = 0
    _ALICE = 1
    _BOB = 2
    _FIRST_URSULA = 5
    _ursulas_range = range(NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS)

    def __init__(self,
                 test_accounts=None,
                 poa=True,
                 eth_airdrop=False,
                 free_transactions=False,
                 *args, **kwargs):

        if test_accounts is None:
            test_accounts = self._default_test_accounts

        super().__init__(provider_process=TEST_PROVIDER_ON_MAIN_PROCESS, *args, **kwargs)
        self.log = Logger("test-blockchain")
        self.attach_middleware(w3=self.interface.w3, poa=poa, free_transactions=free_transactions)

        # Generate additional ethereum accounts for testing
        population = test_accounts
        enough_accounts = len(self.interface.w3.eth.accounts) >= population
        if not enough_accounts:
            accounts_to_make = population - len(self.interface.w3.eth.accounts)
            self.__generate_insecure_unlocked_accounts(quantity=accounts_to_make)
            assert test_accounts == len(self.interface.w3.eth.accounts)

        if eth_airdrop is True:  # ETH for everyone!
            self.ether_airdrop(amount=DEVELOPMENT_ETH_AIRDROP_AMOUNT)

    @staticmethod
    def free_gas_price_strategy(w3, transaction_params=None):
        return 0

    def attach_middleware(self, w3, poa: bool = True, free_transactions: bool = False):

        # For use with Proof-Of-Authority test-blockchains
        if poa:
            w3 = self.interface.w3
            w3.middleware_onion.inject(geth_poa_middleware, layer=0)

        # Free transaction gas!!
        if free_transactions:
            w3.eth.setGasPriceStrategy(self.free_gas_price_strategy)

    @classmethod
    def sever_connection(self) -> None:
        Blockchain._instance = NO_BLOCKCHAIN_AVAILABLE

    def __generate_insecure_unlocked_accounts(self, quantity: int) -> List[str]:

        #
        # Sanity Check - Only PyEVM can be used.
        #

        # Detect provider platform
        client_version = self.interface.w3.clientVersion

        if 'Geth' in client_version:
            raise RuntimeError("WARNING: Geth providers are not implemented.")
        elif "Parity" in client_version:
            raise RuntimeError("WARNING: Parity providers are not implemented.")

        addresses = list()
        for _ in range(quantity):
            address = self.interface.provider.ethereum_tester.add_account('0x' + os.urandom(32).hex())
            addresses.append(address)
            self._test_account_cache.append(address)
            self.log.info('Generated new insecure account {}'.format(address))
        return addresses

    def ether_airdrop(self, amount: int) -> List[str]:
        """Airdrops ether from creator address to all other addresses!"""

        coinbase, *addresses = self.interface.w3.eth.accounts

        tx_hashes = list()
        for address in addresses:

            tx = {'to': address,
                  'from': coinbase,
                  'value': amount}

            txhash = self.interface.w3.eth.sendTransaction(tx)

            _receipt = self.wait_for_receipt(txhash)
            tx_hashes.append(txhash)
            eth_amount = Web3().fromWei(amount, 'ether')
            self.log.info("Airdropped {} ETH {} -> {}".format(eth_amount, tx['from'], tx['to']))

        return tx_hashes

    def time_travel(self, hours: int = None, seconds: int = None, periods: int = None):
        """
        Wait the specified number of wait_hours by comparing
        block timestamps and mines a single block.
        """

        more_than_one_arg = sum(map(bool, (hours, seconds, periods))) > 1
        if more_than_one_arg:
            raise ValueError("Specify hours, seconds, or lock_periods, not a combination")

        if periods:
            duration = (TokenEconomics.hours_per_period * periods) * (60 * 60)
            base = TokenEconomics.hours_per_period * 60 * 60
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

        delta = maya.timedelta(seconds=end_timestamp-now)
        self.log.info(f"Time traveled {delta} "
                      f"| period {epoch_to_period(epoch=end_timestamp)} "
                      f"| epoch {end_timestamp}")

    def sync(self, timeout: int = 0):
        return True

    @classmethod
    def connect(cls, *args, **kwargs) -> 'TesterBlockchain':
        interface = BlockchainDeployerInterface(provider_uri=cls._PROVIDER_URI,
                                                compiler=SolidityCompiler(test_contract_dir=CONTRACT_ROOT),
                                                registry=InMemoryEthereumContractRegistry())

        testerchain = TesterBlockchain(interface=interface, *args, **kwargs)
        return testerchain

    @classmethod
    def bootstrap_network(cls) -> Tuple['TesterBlockchain', Dict[str, EthereumContractAgent]]:
        testerchain = cls.connect()

        origin = testerchain.interface.w3.eth.accounts[0]
        deployer = Deployer(blockchain=testerchain, deployer_address=origin, bare=True)

        _txhashes, agents = deployer.deploy_network_contracts(staker_secret=STAKING_ESCROW_DEPLOYMENT_SECRET,
                                                              policy_secret=POLICY_MANAGER_DEPLOYMENT_SECRET,
                                                              adjudicator_secret=ADJUDICATOR_DEPLOYMENT_SECRET,
                                                              user_escrow_proxy_secret=USER_ESCROW_PROXY_DEPLOYMENT_SECRET)
        return testerchain, agents

    @property
    def etherbase_account(self):
        return self.interface.w3.eth.accounts[self._ETHERBASE]

    @property
    def alice_account(self):
        return self.interface.w3.eth.accounts[self._ALICE]

    @property
    def bob_account(self):
        return self.interface.w3.eth.accounts[self._BOB]

    def ursula_account(self, index):
        if index not in self._ursulas_range:
            raise ValueError(f"Ursula index must be lower than {NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS}")
        return self.interface.w3.eth.accounts[index + self._FIRST_URSULA]

    @property
    def ursulas_accounts(self):
        return [self.ursula_account(i) for i in self._ursulas_range]

    @property
    def unassigned_accounts(self):
        assigned_accounts = set(self.ursulas_accounts + [self.etherbase_account, self.alice_account, self.bob_account])
        accounts = set(self.interface.w3.eth.accounts)
        return list(accounts.difference(assigned_accounts))
