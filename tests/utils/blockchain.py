from typing import List, Union

import maya
from ape.api import AccountAPI
from ape.managers.accounts import TestAccountManager
from eth_tester.exceptions import TransactionFailed
from hexbytes import HexBytes

from nucypher.blockchain.eth.interfaces import (
    BlockchainInterface,
)
from nucypher.blockchain.eth.signers import Signer
from nucypher.blockchain.eth.signers.software import InMemorySigner
from nucypher.utilities.gas_strategies import EXPECTED_CONFIRMATION_TIME_IN_SECONDS
from nucypher.utilities.logging import Logger
from tests.constants import (
    TEST_ETH_PROVIDER_URI,
)


class ReservedTestAccountManager(TestAccountManager):

    NUMBER_OF_URSULAS_IN_TESTS = 10
    NUMBER_OF_STAKING_PROVIDERS_IN_TESTS = NUMBER_OF_URSULAS_IN_TESTS

    # Internal
    __STAKING_PROVIDERS_RANGE = range(NUMBER_OF_STAKING_PROVIDERS_IN_TESTS)
    __OPERATORS_RANGE = range(NUMBER_OF_URSULAS_IN_TESTS)

    # Reserved addresses
    _ETHERBASE = 0
    _ALICE = 1
    _BOB = 2
    _FIRST_STAKING_PROVIDER = 5
    _FIRST_URSULA = _FIRST_STAKING_PROVIDER + NUMBER_OF_STAKING_PROVIDERS_IN_TESTS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__accounts = None

    @property
    def accounts(self) -> List[str]:
        if self.__accounts:
            return self.__accounts

        test_accounts = [test_account.address for test_account in super().accounts]

        self.__accounts = test_accounts
        return test_accounts

    @property
    def ape_accounts(self) -> List[AccountAPI]:
        return list(super(ReservedTestAccountManager, self).accounts)

    @property
    def etherbase_account(self):
        return self[self._ETHERBASE]

    @property
    def alice_account(self):
        return self[self._ALICE]

    @property
    def bob_account(self):
        return self[self._BOB]

    def ursula_account(self, index):
        if index not in self.__OPERATORS_RANGE:
            raise ValueError(
                f"Ursula index must be lower than {self.NUMBER_OF_URSULAS_IN_TESTS}"
            )
        return self[index + self._FIRST_URSULA]

    @property
    def ursulas_accounts(self):
        return list(self.ursula_account(i) for i in self.__OPERATORS_RANGE)

    def stake_provider_account(self, index):
        if index not in self.__STAKING_PROVIDERS_RANGE:
            raise ValueError(
                f"Stake provider index must be lower than {self.NUMBER_OF_URSULAS_IN_TESTS}"
            )
        return self[index + self._FIRST_STAKING_PROVIDER]

    @property
    def stake_providers_accounts(self):
        return list(
            self.stake_provider_account(i) for i in self.__STAKING_PROVIDERS_RANGE
        )

    @property
    def unassigned_accounts(self):
        special_accounts = [
            self.etherbase_account,
            self.alice_account,
            self.bob_account,
        ]
        assigned_accounts = set(
            self.stake_providers_accounts + self.ursulas_accounts + special_accounts
        )
        accounts = set(self.accounts)
        return list(accounts.difference(assigned_accounts))

    def get_ape_account(self, account_address: str) -> AccountAPI:
        account_index = self.accounts.index(account_address)
        ape_account = self.ape_accounts[account_index]
        return ape_account

    def get_account_signer(self, account_address: str) -> Signer:
        ape_account = self.get_ape_account(account_address)
        return InMemorySigner(private_key=ape_account.private_key)


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

    def __init__(
        self,
        poa: bool = True,
        light: bool = False,
        *args,
        **kwargs,
    ):
        EXPECTED_CONFIRMATION_TIME_IN_SECONDS["free"] = 5  # Just some upper-limit
        super().__init__(
            endpoint=self.ETH_PROVIDER_URI,
            poa=poa,
            light=light,
            *args,
            **kwargs,
        )

        self.log = Logger("test-blockchain")
        self.connect()

    def attach_middleware(self):
        pass

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

    def wait_for_receipt(self, txhash: Union[bytes, str, HexBytes], timeout: int = None) -> dict:
        """Wait for a transaction receipt and return it"""
        timeout = timeout or self.TIMEOUT
        result = self.client.wait_for_receipt(transaction_hash=txhash, timeout=timeout)
        if result.status == 0:
            raise TransactionFailed()
        return result

    def get_block_number(self) -> int:
        return self.client.block_number
