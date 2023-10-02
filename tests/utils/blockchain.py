import os
from typing import List, Union

import maya
from eth_tester.exceptions import TransactionFailed
from hexbytes import HexBytes
from web3 import Web3

from nucypher.blockchain.eth.interfaces import (
    BlockchainInterface,
)
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.blockchain.eth.token import NU
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.gas_strategies import EXPECTED_CONFIRMATION_TIME_IN_SECONDS
from nucypher.utilities.logging import Logger
from tests.constants import (
    DEVELOPMENT_ETH_AIRDROP_AMOUNT,
    INSECURE_DEVELOPMENT_PASSWORD,
    NUMBER_OF_ETH_TEST_ACCOUNTS,
    NUMBER_OF_STAKING_PROVIDERS_IN_BLOCKCHAIN_TESTS,
    NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS,
    TEST_ETH_PROVIDER_URI,
)


def token_airdrop(token_agent, amount: NU, transacting_power: TransactingPower, addresses: List[str]):
    """Airdrops tokens from creator address to all other addresses!"""

    signer = Web3Signer(token_agent.blockchain.client)
    signer.unlock_account(account=transacting_power.account, password=INSECURE_DEVELOPMENT_PASSWORD)

    def txs():
        args = {'from': transacting_power.account, 'gasPrice': token_agent.blockchain.client.gas_price}
        for address in addresses:
            contract_function = token_agent.contract.functions.transfer(address, int(amount))
            _receipt = token_agent.blockchain.send_transaction(contract_function=contract_function,
                                                               transacting_power=transacting_power,
                                                               payload=args)
            yield _receipt

    receipts = list()
    for receipt in txs():  # One at a time
        receipts.append(receipt)
    return receipts


def free_gas_price_strategy(w3, transaction_params=None):
    return None


class TesterBlockchain(BlockchainInterface):
    """
    Blockchain subclass with additional test utility methods and options.
    """

    __test__ = False  # prohibit pytest from collecting this object as a test

    # Web3
    GAS_STRATEGIES = {**BlockchainInterface.GAS_STRATEGIES, 'free': free_gas_price_strategy}
    ETH_PROVIDER_URI = TEST_ETH_PROVIDER_URI
    DEFAULT_GAS_STRATEGY = 'free'

    # Reserved addresses
    _ETHERBASE = 0
    _ALICE = 1
    _BOB = 2
    _FIRST_STAKING_PROVIDER = 5
    _FIRST_URSULA = _FIRST_STAKING_PROVIDER + NUMBER_OF_STAKING_PROVIDERS_IN_BLOCKCHAIN_TESTS

    # Internal
    __STAKING_PROVIDERS_RANGE = range(NUMBER_OF_STAKING_PROVIDERS_IN_BLOCKCHAIN_TESTS)
    __OPERATORS_RANGE = range(NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS)
    __ACCOUNT_CACHE = list()

    def __init__(
        self,
        test_accounts: int = NUMBER_OF_ETH_TEST_ACCOUNTS,
        poa: bool = True,
        light: bool = False,
        eth_airdrop: bool = False,
        *args,
        **kwargs,
    ):
        EXPECTED_CONFIRMATION_TIME_IN_SECONDS["free"] = 5  # Just some upper-limit
        super().__init__(
            blockchain_endpoint=self.ETH_PROVIDER_URI,
            poa=poa,
            light=light,
            *args,
            **kwargs,
        )
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

    def attach_middleware(self):
        pass

    def __generate_insecure_unlocked_accounts(self, quantity: int) -> List[str]:

        addresses = list()
        for _ in range(quantity):
            address = self.provider.ethereum_tester.add_account('0x' + os.urandom(32).hex())
            addresses.append(address)
            self.__ACCOUNT_CACHE.append(address)
            self.log.info('Generated new insecure account {}'.format(address))
        return addresses

    def ether_airdrop(self, amount: int) -> List[str]:
        """Airdrops ether from creator address to all other addresses!"""
        coinbase, *addresses = self.client.accounts
        tx_hashes = list()
        for address in addresses:
            tx = {'to': address, 'from': coinbase, 'value': amount, 'gasPrice': self.w3.eth.generate_gas_price()}
            txhash = self.w3.eth.send_transaction(tx)

            _receipt = self.wait_for_receipt(txhash)
            tx_hashes.append(txhash)
            eth_amount = Web3().from_wei(amount, 'ether')
            self.log.info("Airdropped {} ETH {} -> {}".format(eth_amount, tx['from'], tx['to']))

        return tx_hashes

    def time_travel(self,
                    hours: int = None,
                    seconds: int = None):
        """
        Wait the specified number of wait_hours by comparing
        block timestamps and mines a single block.
        """

        more_than_one_arg = sum(map(bool, (hours, seconds))) > 1
        if more_than_one_arg:
            raise ValueError("Specify either hours or seconds, not a combination")

        if hours:
            duration = hours * (60*60)
            base = 60 * 60
        elif seconds:
            duration = seconds
            base = 1
        else:
            raise ValueError("Specify either hours, or seconds.")

        now = self.w3.eth.get_block('latest').timestamp
        end_timestamp = ((now+duration)//base) * base

        self.w3.eth.w3.testing.timeTravel(timestamp=end_timestamp)
        self.w3.eth.w3.testing.mine(1)

        delta = maya.timedelta(seconds=end_timestamp-now)
        self.log.info(f"Time traveled {delta} "
                      f"| epoch {end_timestamp}")

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
        if index not in self.__OPERATORS_RANGE:
            raise ValueError(f"Ursula index must be lower than {NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS}")
        return self.client.accounts[index + self._FIRST_URSULA]

    def stake_provider_account(self, index):
        if index not in self.__STAKING_PROVIDERS_RANGE:
            raise ValueError(f"Stake provider index must be lower than {NUMBER_OF_STAKING_PROVIDERS_IN_BLOCKCHAIN_TESTS}")
        return self.client.accounts[index + self._FIRST_STAKING_PROVIDER]

    @property
    def ursulas_accounts(self):
        return list(self.ursula_account(i) for i in self.__OPERATORS_RANGE)

    @property
    def stake_providers_accounts(self):
        return list(self.stake_provider_account(i) for i in self.__STAKING_PROVIDERS_RANGE)

    @property
    def unassigned_accounts(self):
        special_accounts = [self.etherbase_account, self.alice_account, self.bob_account]
        assigned_accounts = set(self.stake_providers_accounts + self.ursulas_accounts + special_accounts)
        accounts = set(self.client.accounts)
        return list(accounts.difference(assigned_accounts))

    def wait_for_receipt(self, txhash: Union[bytes, str, HexBytes], timeout: int = None) -> dict:
        """Wait for a transaction receipt and return it"""
        timeout = timeout or self.TIMEOUT
        result = self.client.wait_for_receipt(transaction_hash=txhash, timeout=timeout)
        if result.status == 0:
            raise TransactionFailed()
        return result

    def get_block_number(self) -> int:
        return self.client.block_number
