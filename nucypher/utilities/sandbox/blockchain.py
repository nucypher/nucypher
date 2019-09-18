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
from typing import List, Tuple

import maya
from twisted.logger import Logger
from web3 import Web3

from nucypher.blockchain.economics import TokenEconomics, StandardTokenEconomics
from nucypher.blockchain.eth.actors import ContractAdministrator
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.blockchain.eth.token import NU
from nucypher.blockchain.eth.utils import epoch_to_period
from nucypher.config.constants import BASE_DIR
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import (
    NUMBER_OF_ETH_TEST_ACCOUNTS,
    NUMBER_OF_STAKERS_IN_BLOCKCHAIN_TESTS,
    NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS,
    DEVELOPMENT_ETH_AIRDROP_AMOUNT,
    INSECURE_DEVELOPMENT_PASSWORD
)


def token_airdrop(token_agent, amount: NU, origin: str, addresses: List[str]):
    """Airdrops tokens from creator address to all other addresses!"""

    def txs():
        args = {'from': origin, 'gasPrice': token_agent.blockchain.client.gas_price}
        for address in addresses:
            contract_function = token_agent.contract.functions.transfer(address, int(amount))
            _receipt = token_agent.blockchain.send_transaction(contract_function=contract_function,
                                                               sender_address=origin,
                                                               payload=args)
            yield _receipt

    receipts = list()
    for receipt in txs():  # One at a time
        receipts.append(receipt)
    return receipts


class TesterBlockchain(BlockchainDeployerInterface):
    """
    Blockchain subclass with additional test utility methods and options.
    """

    _instance = None

    _PROVIDER_URI = 'tester://pyevm'
    TEST_CONTRACTS_DIR = os.path.join(BASE_DIR, 'tests', 'blockchain', 'eth', 'contracts', 'contracts')
    _compiler = SolidityCompiler(test_contract_dir=TEST_CONTRACTS_DIR)
    _test_account_cache = list()

    _default_test_accounts = NUMBER_OF_ETH_TEST_ACCOUNTS

    # Reserved addresses
    _ETHERBASE = 0
    _ALICE = 1
    _BOB = 2
    _FIRST_STAKER = 5
    _stakers_range = range(NUMBER_OF_STAKERS_IN_BLOCKCHAIN_TESTS)
    _FIRST_URSULA = _FIRST_STAKER + NUMBER_OF_STAKERS_IN_BLOCKCHAIN_TESTS
    _ursulas_range = range(NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS)

    _default_token_economics = StandardTokenEconomics()

    def __init__(self,
                 test_accounts=None,
                 poa=True,
                 eth_airdrop=False,
                 free_transactions=False,
                 compiler: SolidityCompiler = None,
                 *args, **kwargs):

        if not test_accounts:
            test_accounts = self._default_test_accounts
        self.free_transactions = free_transactions

        if compiler:
            TesterBlockchain._compiler = compiler

        super().__init__(provider_uri=self._PROVIDER_URI,
                         provider_process=None,
                         poa=poa,
                         compiler=self._compiler,
                         *args, **kwargs)

        self.log = Logger("test-blockchain")
        self.connect()

        # Generate additional ethereum accounts for testing
        population = test_accounts
        enough_accounts = len(self.client.accounts) >= population
        if not enough_accounts:
            accounts_to_make = population - len(self.client.accounts)
            self.__generate_insecure_unlocked_accounts(quantity=accounts_to_make)
            assert test_accounts == len(self.w3.eth.accounts)

        if eth_airdrop is True:  # ETH for everyone!
            self.ether_airdrop(amount=DEVELOPMENT_ETH_AIRDROP_AMOUNT)

    @staticmethod
    def free_gas_price_strategy(w3, transaction_params=None):
        return 0

    def attach_middleware(self):
        super().attach_middleware()
        if self.free_transactions:
            self.w3.eth.setGasPriceStrategy(self.free_gas_price_strategy)

    def __generate_insecure_unlocked_accounts(self, quantity: int) -> List[str]:

        #
        # Sanity Check - Only PyEVM can be used.
        #

        # Detect provider platform
        client_version = self.w3.clientVersion

        if 'Geth' in client_version:
            raise RuntimeError("WARNING: Geth providers are not implemented.")
        elif "Parity" in client_version:
            raise RuntimeError("WARNING: Parity providers are not implemented.")

        addresses = list()
        for _ in range(quantity):
            address = self.provider.ethereum_tester.add_account('0x' + os.urandom(32).hex())
            addresses.append(address)
            self._test_account_cache.append(address)
            self.log.info('Generated new insecure account {}'.format(address))
        return addresses

    def ether_airdrop(self, amount: int) -> List[str]:
        """Airdrops ether from creator address to all other addresses!"""

        coinbase, *addresses = self.w3.eth.accounts

        tx_hashes = list()
        for address in addresses:
            tx = {'to': address, 'from': coinbase, 'value': amount}
            txhash = self.w3.eth.sendTransaction(tx)

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
            raise ValueError("Specify hours, seconds, or periods, not a combination")

        if periods:
            duration = self._default_token_economics.seconds_per_period * periods
            base = self._default_token_economics.seconds_per_period
        elif hours:
            duration = hours * (60*60)
            base = 60 * 60
        elif seconds:
            duration = seconds
            base = 1
        else:
            raise ValueError("Specify either hours, seconds, or periods.")

        now = self.w3.eth.getBlock(block_identifier='latest').timestamp
        end_timestamp = ((now+duration)//base) * base

        self.w3.eth.web3.testing.timeTravel(timestamp=end_timestamp)
        self.w3.eth.web3.testing.mine(1)

        delta = maya.timedelta(seconds=end_timestamp-now)
        self.log.info(f"Time traveled {delta} "
                      f"| period {epoch_to_period(epoch=end_timestamp, seconds_per_period=self._default_token_economics.seconds_per_period)} "
                      f"| epoch {end_timestamp}")

    @classmethod
    def bootstrap_network(cls,
                          economics: TokenEconomics = None
                          ) -> Tuple['TesterBlockchain', 'InMemoryContractRegistry']:
        """For use with metric testing scripts"""

        registry = InMemoryContractRegistry()
        testerchain = cls(compiler=SolidityCompiler())
        BlockchainInterfaceFactory.register_interface(testerchain)
        power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                 account=testerchain.etherbase_account)
        power.activate()
        testerchain.transacting_power = power

        origin = testerchain.client.etherbase
        deployer = ContractAdministrator(deployer_address=origin, 
                                         registry=registry, 
                                         economics=economics or cls._default_token_economics)
        secrets = dict()
        for deployer_class in deployer.upgradeable_deployer_classes:
            secrets[deployer_class.contract_name] = INSECURE_DEVELOPMENT_PASSWORD
        _receipts = deployer.deploy_network_contracts(secrets=secrets, interactive=False)
        return testerchain, registry

    @property
    def etherbase_account(self):
        return self.client.accounts[self._ETHERBASE]

    @property
    def alice_account(self):
        return self.client.accounts[self._ALICE]

    @property
    def bob_account(self):
        return self.client.accounts[self._BOB]

    def ursula_account(self, index):
        if index not in self._ursulas_range:
            raise ValueError(f"Ursula index must be lower than {NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS}")
        return self.client.accounts[index + self._FIRST_URSULA]

    def staker_account(self, index):
        if index not in self._stakers_range:
            raise ValueError(f"Staker index must be lower than {NUMBER_OF_STAKERS_IN_BLOCKCHAIN_TESTS}")
        return self.client.accounts[index + self._FIRST_STAKER]

    @property
    def ursulas_accounts(self):
        return list(self.ursula_account(i) for i in self._ursulas_range)

    @property
    def stakers_accounts(self):
        return list(self.staker_account(i) for i in self._stakers_range)

    @property
    def unassigned_accounts(self):
        special_accounts = [self.etherbase_account, self.alice_account, self.bob_account]
        assigned_accounts = set(self.stakers_accounts + self.ursulas_accounts + special_accounts)
        accounts = set(self.client.accounts)
        return list(accounts.difference(assigned_accounts))

    def wait_for_receipt(self, txhash: bytes, timeout: int = None) -> dict:
        """Wait for a transaction receipt and return it"""
        timeout = timeout or self.TIMEOUT
        result = self.w3.eth.waitForTransactionReceipt(txhash, timeout=timeout)
        return result

