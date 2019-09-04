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

from eth_tester.exceptions import TransactionFailed

from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.utilities.sandbox.constants import MOCK_IP_ADDRESS, MOCK_IP_ADDRESS_2, MAX_TEST_SEEDER_ENTRIES, \
    MOCK_URSULA_STARTING_PORT


@pytest.mark.slow()
def test_seeder(testerchain, deploy_contract):
    origin, seed_address, another_seed_address, *everyone_else = testerchain.client.accounts
    seed = (MOCK_IP_ADDRESS, MOCK_URSULA_STARTING_PORT)
    another_seed = (MOCK_IP_ADDRESS_2, MOCK_URSULA_STARTING_PORT + 1)

    contract, _txhash = deploy_contract('Seeder', MAX_TEST_SEEDER_ENTRIES)

    assert contract.functions.getSeedArrayLength().call() == MAX_TEST_SEEDER_ENTRIES
    assert contract.functions.owner().call() == origin

    with pytest.raises((TransactionFailed, ValueError)):
        txhash = contract.functions.enroll(seed_address, *seed).transact({'from': seed_address})
        testerchain.wait_for_receipt(txhash)
    with pytest.raises((TransactionFailed, ValueError)):
        txhash = contract.functions.refresh(*seed).transact({'from': seed_address})
        testerchain.wait_for_receipt(txhash)

    txhash = contract.functions.enroll(seed_address, *seed).transact({'from': origin})
    testerchain.wait_for_receipt(txhash)
    assert contract.functions.seeds(seed_address).call() == [*seed]
    assert contract.functions.seedArray(0).call() == seed_address
    assert contract.functions.seedArray(1).call() == BlockchainInterface.NULL_ADDRESS
    txhash = contract.functions.enroll(another_seed_address, *another_seed).transact({'from': origin})
    testerchain.wait_for_receipt(txhash)
    assert contract.functions.seeds(another_seed_address).call() == [*another_seed]
    assert contract.functions.seedArray(0).call() == seed_address
    assert contract.functions.seedArray(1).call() == another_seed_address
    assert contract.functions.seedArray(2).call() == BlockchainInterface.NULL_ADDRESS

    txhash = contract.functions.refresh(*another_seed).transact({'from': seed_address})
    testerchain.wait_for_receipt(txhash)
    assert contract.functions.seedArray(0).call() == seed_address
    assert contract.functions.seeds(seed_address).call() == [*another_seed]
