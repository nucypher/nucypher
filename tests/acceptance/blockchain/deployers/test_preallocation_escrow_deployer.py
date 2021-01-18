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

from nucypher.blockchain.eth.deployers import (AdjudicatorDeployer, NucypherTokenDeployer, PolicyManagerDeployer,
                                               PreallocationEscrowDeployer, StakingEscrowDeployer,
                                               StakingInterfaceDeployer, StakingInterfaceRouterDeployer)

preallocation_escrow_contracts = list()
NUMBER_OF_PREALLOCATIONS = 50


def test_staking_interface_deployer(testerchain, deployment_progress, test_registry):

    #
    # Setup
    #

    origin = testerchain.etherbase_account

    token_deployer = NucypherTokenDeployer(deployer_address=origin, registry=test_registry)
    token_deployer.deploy()

    policy_manager_deployer = PolicyManagerDeployer(deployer_address=origin, registry=test_registry)
    policy_manager_deployer.deploy()

    adjudicator_deployer = AdjudicatorDeployer(deployer_address=origin, registry=test_registry)
    adjudicator_deployer.deploy()

    staking_escrow_deployer = StakingEscrowDeployer(deployer_address=origin, registry=test_registry)
    staking_escrow_deployer.deploy()

    #
    # Test
    #

    staking_interface_deployer = StakingInterfaceDeployer(deployer_address=origin, registry=test_registry)
    staking_interface_receipts = staking_interface_deployer.deploy(progress=deployment_progress)

    # deployment steps must match expected number of steps
    assert deployment_progress.num_steps == len(staking_interface_deployer.deployment_steps) == 2
    assert len(staking_interface_receipts) == 2

    for step in staking_interface_deployer.deployment_steps:
        assert staking_interface_receipts[step]['status'] == 1


def test_deploy_multiple_preallocations(testerchain, test_registry):

    deployer_account = testerchain.etherbase_account

    router = testerchain.get_contract_by_name(registry=test_registry, contract_name=StakingInterfaceRouterDeployer.contract_name)
    router_address = router.address
    for index in range(NUMBER_OF_PREALLOCATIONS):
        deployer = PreallocationEscrowDeployer(deployer_address=deployer_account, registry=test_registry)

        deployment_receipt = deployer.deploy()
        assert deployment_receipt['status'] == 1

        preallocation_escrow_contract = deployer.contract
        router = preallocation_escrow_contract.functions.router().call()
        assert router == router_address

        preallocation_escrow_contracts.append(preallocation_escrow_contract)

        # simulates passage of time / blocks
        if index % 5 == 0:
            testerchain.w3.eth.web3.testing.mine(1)
            testerchain.time_travel(seconds=5)

    assert len(preallocation_escrow_contracts) == NUMBER_OF_PREALLOCATIONS


def test_upgrade_staking_interface(testerchain, test_registry):

    router = testerchain.get_contract_by_name(registry=test_registry,
                                              contract_name=StakingInterfaceRouterDeployer.contract_name)

    contract = testerchain.get_contract_by_name(registry=test_registry,
                                                contract_name=StakingInterfaceDeployer.contract_name,
                                                proxy_name=StakingInterfaceRouterDeployer.contract_name,
                                                use_proxy_address=False)

    target = router.functions.target().call()
    assert target == contract.address

    staking_interface_deployer = StakingInterfaceDeployer(deployer_address=testerchain.etherbase_account,
                                                          registry=test_registry)

    receipts = staking_interface_deployer.upgrade(ignore_deployed=True, confirmations=0)

    assert len(receipts) == 2

    for title, receipt in receipts.items():
        assert receipt['status'] == 1

    for preallocation_escrow_contract in preallocation_escrow_contracts:
        router_address = preallocation_escrow_contract.functions.router().call()
        assert router.address == router_address

    new_target = router.functions.target().call()
    contract = testerchain.get_contract_by_name(registry=test_registry,
                                                contract_name=StakingInterfaceDeployer.contract_name,
                                                proxy_name=StakingInterfaceRouterDeployer.contract_name,
                                                use_proxy_address=False)
    assert new_target == contract.address
    assert new_target != target
