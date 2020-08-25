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

import random

import pytest

from nucypher.blockchain.eth.deployers import PreallocationEscrowDeployer


def test_deploy_and_allocate(agency, token_economics, test_registry):
    token_agent, staking_agent, policy_agent = agency
    testerchain = policy_agent.blockchain
    origin = testerchain.etherbase_account

    deployments = dict()
    allocation = token_economics.minimum_allowed_locked * 1
    number_of_deployments = 1

    _last_deployment_address = None
    for index in range(number_of_deployments):
        escrow_deployer = PreallocationEscrowDeployer(deployer_address=origin, registry=test_registry)

        _deployment_txhashes = escrow_deployer.deploy()

        # Ensure we have the correct assembly of address and abi
        assert escrow_deployer.contract.address == escrow_deployer.contract.address

        # Ensure each deployment is unique
        if _last_deployment_address:
            assert escrow_deployer.contract.address != _last_deployment_address
        _last_deployment_address = escrow_deployer.contract.address

        deployments[escrow_deployer.contract.address] = escrow_deployer
    assert len(deployments) == number_of_deployments

    # Let some time pass
    testerchain.time_travel(hours=3)
    assert token_agent.get_balance(address=origin) > 1

    # Start allocating tokens
    for address, deployer in deployments.items():
        assert deployer.deployer_address == origin

        deployer.initial_deposit(value=allocation, duration_seconds=token_economics.maximum_rewarded_periods)

        beneficiary = random.choice(testerchain.unassigned_accounts)
        _assign_receipt = deployer.assign_beneficiary(beneficiary)

    assert number_of_deployments == len(deployments)
