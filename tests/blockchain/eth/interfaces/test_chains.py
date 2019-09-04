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


import pytest

from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
# Prevents TesterBlockchain to be picked up by py.test as a test class
from nucypher.utilities.sandbox.blockchain import TesterBlockchain as _TesterBlockchain
from nucypher.utilities.sandbox.constants import (
    DEVELOPMENT_ETH_AIRDROP_AMOUNT,
    NUMBER_OF_ETH_TEST_ACCOUNTS,
    NUMBER_OF_STAKERS_IN_BLOCKCHAIN_TESTS,
    NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS,
    TEST_PROVIDER_URI
)


@pytest.fixture()
def another_testerchain(solidity_compiler):
    testerchain = _TesterBlockchain(eth_airdrop=True, free_transactions=True)
    testerchain.deployer_address = testerchain.etherbase_account
    yield testerchain


def test_testerchain_creation(testerchain, another_testerchain):

    chains = (testerchain, another_testerchain)

    for chain in chains:

        # Ensure we are testing on the correct network...
        assert 'tester' in chain.provider_uri

        # ... and that there are already some blocks mined
        assert chain.w3.eth.blockNumber > 0

        # Check that we have enough test accounts
        assert len(chain.client.accounts) >= NUMBER_OF_ETH_TEST_ACCOUNTS

        # Check that distinguished accounts are assigned
        etherbase = chain.etherbase_account
        assert etherbase == chain.client.accounts[0]

        alice = chain.alice_account
        assert alice == chain.client.accounts[1]

        bob = chain.bob_account
        assert bob == chain.client.accounts[2]

        stakers = [chain.staker_account(i) for i in range(NUMBER_OF_STAKERS_IN_BLOCKCHAIN_TESTS)]
        assert stakers == chain.stakers_accounts

        ursulas = [chain.ursula_account(i) for i in range(NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS)]
        assert ursulas == chain.ursulas_accounts

        # Check that the remaining accounts are different from the previous ones:
        assert set([etherbase, alice, bob] + ursulas + stakers).isdisjoint(set(chain.unassigned_accounts))

        # Check that accounts are funded
        for account in chain.client.accounts:
            assert chain.client.get_balance(account) >= DEVELOPMENT_ETH_AIRDROP_AMOUNT

        # Check that accounts can send transactions
        for account in chain.client.accounts:
            balance = chain.client.get_balance(account)
            assert balance

            tx = {'to': etherbase, 'from': account, 'value': 100}
            txhash = chain.client.send_transaction(tx)
            _receipt = chain.wait_for_receipt(txhash)
