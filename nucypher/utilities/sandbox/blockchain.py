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
from twisted.logger import Logger

from constant_sorrow.constants import NO_BLOCKCHAIN_AVAILABLE
from typing import List
from umbral.keys import UmbralPrivateKey
from web3.middleware import geth_poa_middleware

from nucypher.blockchain.eth import constants
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.utilities.sandbox.constants import (DEVELOPMENT_ETH_AIRDROP_AMOUNT,
                                                  DEFAULT_NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK,
                                                  TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD)


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

    _instance = NO_BLOCKCHAIN_AVAILABLE
    _test_account_cache = list()

    def __init__(self, test_accounts=None, poa=True, airdrop=True, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.log = Logger("test-blockchain")  # type: Logger

        # For use with Proof-Of-Authority test-blockchains
        if poa is True:
            w3 = self.interface.w3
            w3.middleware_stack.inject(geth_poa_middleware, layer=0)

        # Generate additional ethereum accounts for testing
        enough_accounts = len(self.interface.w3.eth.accounts) >= DEFAULT_NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK
        if test_accounts is not None and not enough_accounts:

            accounts_to_make = DEFAULT_NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK - len(self.interface.w3.eth.accounts)
            test_accounts = test_accounts if test_accounts is not None else DEFAULT_NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK

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
        insecure_passphrase = TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD
        for _ in range(quantity):

            umbral_priv_key = UmbralPrivateKey.gen_key()
            address = self.interface.w3.personal.importRawKey(private_key=umbral_priv_key.to_bytes(),
                                                              passphrase=insecure_passphrase)

            assert self.interface.unlock_account(address, password=insecure_passphrase, duration=None), 'Failed to unlock {}'.format(address)
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
