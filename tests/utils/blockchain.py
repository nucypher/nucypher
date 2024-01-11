from itertools import islice
from typing import Union, List

import maya
from ape.api import AccountAPI
from ape.managers.accounts import TestAccountManager
from eth_account import Account as EthAccount
from eth_keys.datatypes import PrivateKey
from hexbytes import HexBytes
from web3.types import TxReceipt
from eth_account.signers.local import LocalAccount as EthLocalAccount
from nucypher.blockchain.eth.accounts import LocalAccount
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.utilities.gas_strategies import EXPECTED_CONFIRMATION_TIME_IN_SECONDS
from tests.constants import TEST_ETH_PROVIDER_URI


def free_gas_price_strategy(w3, transaction_params=None):
    return None


class TestAccount(LocalAccount):

    @classmethod
    def random(cls, *args, **kwargs) -> 'LocalAccount':
        account = EthAccount.create(*args, **kwargs)
        return cls(key=PrivateKey(account.key), account=EthAccount)

    @classmethod
    def from_key(cls, private_key: PrivateKey) -> 'LocalAccount':
        account = EthAccount.from_key(private_key=private_key)
        return cls(key=PrivateKey(account.key), account=EthAccount)


class ReservedTestAccountManager(TestAccountManager):

    NUMBER_OF_URSULAS_IN_TESTS = 10
    NUMBER_OF_STAKING_PROVIDERS_IN_TESTS = NUMBER_OF_URSULAS_IN_TESTS

    __STAKING_PROVIDERS_RANGE = range(NUMBER_OF_STAKING_PROVIDERS_IN_TESTS)
    __OPERATORS_RANGE = range(NUMBER_OF_URSULAS_IN_TESTS)

    _ETHERBASE = 0
    _ALICE = 1
    _BOB = 2
    _FIRST_STAKING_PROVIDER = 5
    _FIRST_URSULA = _FIRST_STAKING_PROVIDER + NUMBER_OF_STAKING_PROVIDERS_IN_TESTS
    _FIRST_UNASSIGNED = _FIRST_URSULA + NUMBER_OF_URSULAS_IN_TESTS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__wallets = None

    @property
    def accounts(self) -> List[TestAccount]:
        if self.__wallets:
            return self.__wallets
        wallets = [TestAccount.from_key(a.private_key) for a in super(ReservedTestAccountManager, self).accounts]
        self.__wallets = wallets
        return wallets

    @property
    def ape_accounts(self) -> List[AccountAPI]:
        return list(super(ReservedTestAccountManager, self).accounts)

    @property
    def etherbase_wallet(self):
        return self[self._ETHERBASE]

    @property
    def alice_wallet(self):
        return self[self._ALICE]

    @property
    def bob_wallet(self):
        return self[self._BOB]

    def ursula_wallet(self, index: int):
        if index not in self.__OPERATORS_RANGE:
            raise ValueError(f"Ursula index must be lower than {self.NUMBER_OF_URSULAS_IN_TESTS}")
        return self[self._FIRST_URSULA + index]

    def provider_wallet(self, index: int):
        if index not in self.__STAKING_PROVIDERS_RANGE:
            raise ValueError(f"Stake provider index must be lower than {self.NUMBER_OF_STAKING_PROVIDERS_IN_TESTS}")
        return self[self._FIRST_STAKING_PROVIDER + index]

    @property
    def ursula_wallets(self):
        return list(self.ursula_wallet(i) for i in self.__OPERATORS_RANGE)

    @property
    def stake_provider_wallets(self):
        return list(self.provider_wallet(i) for i in self.__STAKING_PROVIDERS_RANGE)

    @property
    def unassigned_wallets(self):
        accounts = list(islice(self.accounts, self._FIRST_UNASSIGNED, None))
        return accounts

    @property
    def provider_to_operator(self):
        wallets = zip(self.stake_provider_wallets, self.ursula_wallets)
        return {k.address: v.address for k, v in wallets}

    @property
    def operator_to_provider(self):
        wallets = zip(self.ursula_wallets, self.stake_provider_wallets)
        return {k.address: v.address for k, v in wallets}


class TesterBlockchain(BlockchainInterface):
    __test__ = False  # prohibit pytest from collecting this object as a test

    # Web3
    GAS_STRATEGIES = {**BlockchainInterface.GAS_STRATEGIES, 'free': free_gas_price_strategy}
    ETH_PROVIDER_URI = TEST_ETH_PROVIDER_URI
    DEFAULT_GAS_STRATEGY = 'free'

    def __init__(self, *args, **kwargs):
        EXPECTED_CONFIRMATION_TIME_IN_SECONDS["free"] = 5  # Just some upper-limit
        super().__init__(endpoint=self.ETH_PROVIDER_URI, *args, **kwargs)
        self.accounts = ReservedTestAccountManager()
        self.connect()

    def wait_for_receipt(self, txhash: Union[bytes, str, HexBytes], timeout: int = None) -> TxReceipt:
        timeout = timeout or self.TIMEOUT
        result = self.client.wait_for_receipt(transaction_hash=txhash, timeout=timeout)
        return result

    def time_travel(self, hours: int = None, seconds: int = None):
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
