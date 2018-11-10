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
# import pytest
import pytest

from eth_tester.exceptions import TransactionFailed

TEST_MAX_SEEDS = 20

#
# def test_seeder(testerchain):
#     origin, *everyone_else = testerchain.interface.w3.eth.accounts
#     deployer = SeederDeployer(deployer_address=origin)
#
#     agent = deployer.make_agent()
#     direct_agent = SeederAgent()
#
#     assert agent == direct_agent
#


@pytest.mark.slow()
def test_seeder(testerchain):
    origin, seed_address, another_seed_address, *everyone_else = testerchain.interface.w3.eth.accounts
    seed = ('0.0.0.0', 5757)
    another_seed = ('10.10.10.10', 9151)

    contract, _txhash = testerchain.interface.deploy_contract('Seeder', TEST_MAX_SEEDS)

    assert contract.functions.getSeedArrayLength().call() == TEST_MAX_SEEDS
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
    assert contract.functions.seedArray(1).call() == "0x" + "0" * 40
    txhash = contract.functions.enroll(another_seed_address, *another_seed).transact({'from': origin})
    testerchain.wait_for_receipt(txhash)
    assert contract.functions.seeds(another_seed_address).call() == [*another_seed]
    assert contract.functions.seedArray(0).call() == seed_address
    assert contract.functions.seedArray(1).call() == another_seed_address
    assert contract.functions.seedArray(2).call() == "0x" + "0" * 40

    txhash = contract.functions.refresh(*another_seed).transact({'from': seed_address})
    testerchain.wait_for_receipt(txhash)
    assert contract.functions.seedArray(0).call() == seed_address
    assert contract.functions.seeds(seed_address).call() == [*another_seed]
