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
from web3.contract import Contract


@pytest.fixture()
def escrow(testerchain, deploy_contract):
    # Creator deploys the escrow
    escrow, _ = deploy_contract('StakingEscrowForPolicyMock', 1)
    return escrow


@pytest.fixture(params=[False, True])
def policy_manager(testerchain, escrow, request, deploy_contract):
    creator, client, bad_node, node1, node2, node3, *everyone_else = testerchain.client.accounts

    # Creator deploys the policy manager
    contract, _ = deploy_contract('PolicyManager', escrow.address, 0)

    # Give client some ether
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': client, 'value': 10000})
    testerchain.wait_for_receipt(tx)

    if request.param:
        dispatcher, _ = deploy_contract('Dispatcher', contract.address)

        # Deploy second version of the government contract
        contract = testerchain.client.get_contract(
            abi=contract.abi,
            address=dispatcher.address,
            ContractFactoryClass=Contract)

    tx = escrow.functions.setPolicyManager(contract.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Travel to the start of the next period to prevent problems with unexpected overflow first period
    testerchain.time_travel(hours=1)

    # Register nodes
    tx = escrow.functions.register(node1).transact()
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.register(node2).transact()
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.register(node3).transact()
    testerchain.wait_for_receipt(tx)

    return contract
