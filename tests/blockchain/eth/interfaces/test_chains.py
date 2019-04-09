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
import web3

from nucypher.blockchain.eth.constants import (NUMBER_OF_ETH_TEST_ACCOUNTS,
                                               NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS)
from nucypher.utilities.sandbox.constants import TESTING_ETH_AIRDROP_AMOUNT


def test_testerchain_creation(testerchain):
    # Ensure we are testing on the correct network...
    assert 'tester' in testerchain.interface.provider_uri

    # ... and that there are already some blocks mined
    assert testerchain.interface.w3.eth.blockNumber > 0

    # Check that we have enough test accounts
    assert len(testerchain.interface.w3.eth.accounts) >= NUMBER_OF_ETH_TEST_ACCOUNTS

    # Check that distinguished accounts are assigned
    etherbase = testerchain.etherbase_account
    assert etherbase == testerchain.interface.w3.eth.accounts[0]

    alice = testerchain.alice_account
    assert alice == testerchain.interface.w3.eth.accounts[1]

    bob = testerchain.bob_account
    assert bob == testerchain.interface.w3.eth.accounts[2]

    ursulas = [testerchain.ursula_account(i) for i in range(NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS)]
    assert ursulas == testerchain.ursulas_accounts

    # Check that accounts are funded
    for account in testerchain.interface.w3.eth.accounts:
        assert testerchain.interface.w3.eth.getBalance(account) >= TESTING_ETH_AIRDROP_AMOUNT

