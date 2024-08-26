from functools import cached_property, singledispatchmethod
from typing import List, Union

import maya
from ape.api import AccountAPI
from ape.managers.accounts import TestAccountManager
from eth_tester.exceptions import TransactionFailed
from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address
from hexbytes import HexBytes

from nucypher.blockchain.eth.interfaces import (
    BlockchainInterface,
)
from nucypher.blockchain.eth.signers import Signer
from nucypher.blockchain.eth.signers.software import InMemorySigner
from nucypher.utilities.gas_strategies import EXPECTED_CONFIRMATION_TIME_IN_SECONDS
from nucypher.utilities.logging import Logger
from tests.constants import NUMBER_OF_ETH_TEST_ACCOUNTS, TEST_ETH_PROVIDER_URI


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
    _FIRST_STAKING_PROVIDER = 3
    _FIRST_URSULA = _FIRST_STAKING_PROVIDER + NUMBER_OF_STAKING_PROVIDERS_IN_TESTS

    # Unassigned
    _FIRST_UNASSIGNED = _FIRST_URSULA + NUMBER_OF_URSULAS_IN_TESTS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__ape_accounts = None

    @cached_property
    def accounts_addresses(self) -> List[str]:
        test_accounts = [account.address for account in self.accounts]
        return test_accounts

    @property
    def accounts(self) -> List[AccountAPI]:
        if self.__ape_accounts:
            return self.__ape_accounts

        test_accounts = [test_account for test_account in list(super().accounts)]

        # additional accounts only needed/applicable for unit/integration tests since acceptance
        # tests use a ape-config.yml to specify number of accounts.
        additional_required_accounts = NUMBER_OF_ETH_TEST_ACCOUNTS - len(test_accounts)
        if additional_required_accounts > 0:
            for i in range(additional_required_accounts):
                new_test_account = super(
                    ReservedTestAccountManager, self
                ).generate_test_account()
                test_accounts.append(new_test_account)

        self.__ape_accounts = test_accounts
        return test_accounts

    @singledispatchmethod
    def __getitem__(self, account_id):
        raise NotImplementedError(f"Cannot use {type(account_id)} as account ID.")

    @__getitem__.register
    def __getitem_int(self, account_id: int):
        account = self.accounts[account_id]
        return account

    @__getitem__.register
    def __getitem_str(self, account_str: str):
        account_id = to_checksum_address(account_str)
        for account in self.accounts:
            if account.address == account_id:
                return account

        raise KeyError(f"test account '{account_str}' not found")

    @property
    def etherbase_account(self) -> ChecksumAddress:
        return self[self._ETHERBASE].address

    @property
    def alice_account(self) -> ChecksumAddress:
        return self[self._ALICE].address

    @property
    def bob_account(self) -> ChecksumAddress:
        return self[self._BOB].address

    def ursula_account(self, index):
        if index not in self.__OPERATORS_RANGE:
            raise ValueError(
                f"Ursula index must be lower than {self.NUMBER_OF_URSULAS_IN_TESTS}"
            )
        return self[index + self._FIRST_URSULA].address

    @property
    def ursulas_accounts(self) -> List[ChecksumAddress]:
        return list(self.ursula_account(i) for i in self.__OPERATORS_RANGE)

    def staking_provider_account(self, index) -> ChecksumAddress:
        if index not in self.__STAKING_PROVIDERS_RANGE:
            raise ValueError(
                f"Stake provider index must be lower than {self.NUMBER_OF_URSULAS_IN_TESTS}"
            )
        return self[index + self._FIRST_STAKING_PROVIDER].address

    @property
    def staking_providers_accounts(self) -> List[ChecksumAddress]:
        return list(
            self.staking_provider_account(i) for i in self.__STAKING_PROVIDERS_RANGE
        )

    @property
    def unassigned_accounts(self) -> List[ChecksumAddress]:
        unassigned = [
            account.address for account in self.accounts[self._FIRST_UNASSIGNED :]
        ]
        return unassigned

    def get_account_signer(self, account_address: str) -> Signer:
        return InMemorySigner(private_key=self[account_address].private_key)


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
