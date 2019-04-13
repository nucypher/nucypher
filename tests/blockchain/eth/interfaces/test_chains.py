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

from nucypher.blockchain.eth.constants import (NUMBER_OF_ETH_TEST_ACCOUNTS,
                                               NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS)
from nucypher.utilities.sandbox.constants import TESTING_ETH_AIRDROP_AMOUNT

from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import InMemoryEthereumContractRegistry
from nucypher.utilities.sandbox.blockchain import TesterBlockchain


@pytest.fixture()
def another_testerchain(solidity_compiler):
    memory_registry = InMemoryEthereumContractRegistry()
    deployer_interface = BlockchainDeployerInterface(compiler=solidity_compiler,
                                                     registry=memory_registry,
                                                     provider_uri='tester://pyevm')
    testerchain = TesterBlockchain(interface=deployer_interface,
                                   test_accounts=2*NUMBER_OF_ETH_TEST_ACCOUNTS,
                                   airdrop=True)
    deployer_interface.deployer_address = testerchain.etherbase_account
    yield testerchain
    testerchain.sever_connection()


def test_testerchain_creation(testerchain, another_testerchain):

    chains = (testerchain, another_testerchain)

    for testerchain in chains:

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

        # Check that the remaining accounts are different from the previous ones:
        assert set([etherbase, alice, bob] + ursulas).isdisjoint(set(testerchain.unassigned_accounts))

        # Check that accounts are funded
        for account in testerchain.interface.w3.eth.accounts:
            assert testerchain.interface.w3.eth.getBalance(account) >= TESTING_ETH_AIRDROP_AMOUNT

        # Check that accounts can send transactions
        for account in testerchain.interface.w3.eth.accounts:
            tx = {'to': etherbase, 'from': account, 'value': 100}
            txhash = testerchain.interface.w3.eth.sendTransaction(tx)
            _receipt = testerchain.wait_for_receipt(txhash)
