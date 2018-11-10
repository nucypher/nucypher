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
import pytest
from web3.contract import Contract


VALUE_FIELD = 0
DECIMALS_FIELD = 1
CONFIRMED_PERIOD_1_FIELD = 2
CONFIRMED_PERIOD_2_FIELD = 3
LAST_ACTIVE_PERIOD_FIELD = 4

secret = (123456).to_bytes(32, byteorder='big')


@pytest.fixture()
def token(testerchain):
    # Create an ERC20 token
    token, _ = testerchain.interface.deploy_contract('NuCypherToken', 2 * 10 ** 9)
    return token


@pytest.fixture(params=[False, True])
def escrow_contract(testerchain, token, request):
    def make_escrow(max_allowed_locked_tokens):
        # Creator deploys the escrow
        contract, _ = testerchain.interface.deploy_contract(
            'MinersEscrow', token.address, 1, 4 * 2 * 10 ** 7, 4, 4, 2, 100, max_allowed_locked_tokens)

        if request.param:
            secret_hash = testerchain.interface.w3.sha3(secret)
            dispatcher, _ = testerchain.interface.deploy_contract('Dispatcher', contract.address, secret_hash)
            contract = testerchain.interface.w3.eth.contract(
                abi=contract.abi,
                address=dispatcher.address,
                ContractFactoryClass=Contract)

        policy_manager, _ = testerchain.interface.deploy_contract(
            'PolicyManagerForMinersEscrowMock', token.address, contract.address
        )
        tx = contract.functions.setPolicyManager(policy_manager.address).transact()
        testerchain.wait_for_receipt(tx)
        assert policy_manager.address == contract.functions.policyManager().call()
        # Travel to the start of the next period to prevent problems with unexpected overflow first period
        testerchain.time_travel(hours=1)
        return contract

    return make_escrow
