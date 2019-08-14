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
from eth_utils import keccak

from nucypher.blockchain.eth.token import NU

VALUE_FIELD = 0

secret = (123456).to_bytes(32, byteorder='big')


@pytest.fixture()
def token(testerchain, deploy_contract):
    # Create an ERC20 token
    token, _ = deploy_contract('NuCypherToken', _totalSupply=int(NU(2 * 10 ** 9, 'NuNit')))
    return token


@pytest.fixture(params=[False, True])
def escrow_contract(testerchain, token, request, deploy_contract):
    def make_escrow(max_allowed_locked_tokens):
        # Creator deploys the escrow
        _staking_coefficient = 2 * 10 ** 7
        contract, _ = deploy_contract(
            contract_name='StakingEscrow',
            _token=token.address,
            _hoursPerPeriod=1,
            _miningCoefficient=4 * _staking_coefficient,
            _lockedPeriodsCoefficient=4,
            _rewardedPeriods=4,
            _minLockedPeriods=2,
            _minAllowableLockedTokens=100,
            _maxAllowableLockedTokens=max_allowed_locked_tokens,
            _minWorkerPeriods=1
        )

        if request.param:
            secret_hash = keccak(secret)
            dispatcher, _ = deploy_contract('Dispatcher', contract.address, secret_hash)
            contract = testerchain.client.get_contract(
                abi=contract.abi,
                address=dispatcher.address,
                ContractFactoryClass=Contract)

        policy_manager, _ = deploy_contract(
            'PolicyManagerForStakingEscrowMock', token.address, contract.address
        )
        tx = contract.functions.setPolicyManager(policy_manager.address).transact()
        testerchain.wait_for_receipt(tx)
        assert policy_manager.address == contract.functions.policyManager().call()
        # Travel to the start of the next period to prevent problems with unexpected overflow first period
        testerchain.time_travel(hours=1)
        return contract

    return make_escrow
