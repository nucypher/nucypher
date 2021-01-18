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

from constant_sorrow.constants import BARE

from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent
from nucypher.blockchain.eth.deployers import (DispatcherDeployer, StakingEscrowDeployer)


def test_staking_escrow_deployment(staking_escrow_deployer, deployment_progress):
    deployment_receipts = staking_escrow_deployer.deploy(progress=deployment_progress)

    # deployment steps must match expected number of steps
    assert deployment_progress.num_steps == len(staking_escrow_deployer.deployment_steps) == len(deployment_receipts) == 7

    for step in staking_escrow_deployer.deployment_steps:
        assert deployment_receipts[step]['status'] == 1


def test_make_agent(staking_escrow_deployer, test_registry):
    # Create a StakingEscrowAgent instance
    staking_agent = staking_escrow_deployer.make_agent()

    # Retrieve the StakingEscrowAgent singleton
    same_staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    assert staking_agent == same_staking_agent

    # Compare the contract address for equality
    assert staking_agent.contract_address == same_staking_agent.contract_address


def test_deployment_parameters(staking_escrow_deployer,
                               token_deployer,
                               token_economics,
                               test_registry):

    token_address = staking_escrow_deployer.contract.functions.token().call()
    assert token_deployer.contract_address == token_address

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    params = staking_agent.staking_parameters()
    assert token_economics.staking_deployment_parameters[2:] == params[2:]
    assert token_economics.staking_deployment_parameters[1] == params[1] // params[3]
    assert token_economics.staking_deployment_parameters[0]*60*60 == params[0]  # FIXME: Do we really want this?


def test_staking_escrow_has_dispatcher(staking_escrow_deployer, testerchain, test_registry):

    # Let's get the "bare" StakingEscrow contract (i.e., unwrapped, no dispatcher)
    existing_bare_contract = testerchain.get_contract_by_name(registry=test_registry,
                                                              contract_name=staking_escrow_deployer.contract_name,
                                                              proxy_name=DispatcherDeployer.contract_name,
                                                              use_proxy_address=False)

    # This contract shouldn't be accessible directly through the deployer or the agent
    assert staking_escrow_deployer.contract_address != existing_bare_contract.address
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    assert staking_agent.contract_address != existing_bare_contract

    # The wrapped contract, on the other hand, points to the bare one.
    target = staking_escrow_deployer.contract.functions.target().call()
    assert target == existing_bare_contract.address


def test_upgrade(testerchain, test_registry, token_economics):

    deployer = StakingEscrowDeployer(registry=test_registry,
                                     economics=token_economics,
                                     deployer_address=testerchain.etherbase_account)

    receipts = deployer.upgrade(ignore_deployed=True, confirmations=0)
    for title, receipt in receipts.items():
        assert receipt['status'] == 1


def test_rollback(testerchain, test_registry):

    deployer = StakingEscrowDeployer(registry=test_registry,
                                     deployer_address=testerchain.etherbase_account)

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    current_target = staking_agent.contract.functions.target().call()

    # Let's do one more upgrade
    receipts = deployer.upgrade(ignore_deployed=True, confirmations=0)

    for title, receipt in receipts.items():
        assert receipt['status'] == 1

    old_target = current_target
    current_target = staking_agent.contract.functions.target().call()
    assert current_target != old_target

    # It's time to rollback.
    receipt = deployer.rollback()
    assert receipt['status'] == 1

    new_target = staking_agent.contract.functions.target().call()
    assert new_target != current_target
    assert new_target == old_target


def test_deploy_bare_upgradeable_contract_deployment(testerchain, test_registry, token_economics):
    deployer = StakingEscrowDeployer(registry=test_registry,
                                     deployer_address=testerchain.etherbase_account,
                                     economics=token_economics)

    enrolled_names = list(test_registry.enrolled_names)
    old_number_of_enrollments = enrolled_names.count(StakingEscrowDeployer.contract_name)
    old_number_of_proxy_enrollments = enrolled_names.count(StakingEscrowDeployer._proxy_deployer.contract_name)

    receipts = deployer.deploy(deployment_mode=BARE, ignore_deployed=True)
    for title, receipt in receipts.items():
        assert receipt['status'] == 1

    enrolled_names = list(test_registry.enrolled_names)
    new_number_of_enrollments = enrolled_names.count(StakingEscrowDeployer.contract_name)
    new_number_of_proxy_enrollments = enrolled_names.count(StakingEscrowDeployer._proxy_deployer.contract_name)

    # The principal contract was deployed.
    assert new_number_of_enrollments == (old_number_of_enrollments + 1)

    # The Dispatcher was not deployed.
    assert new_number_of_proxy_enrollments == old_number_of_proxy_enrollments


def test_deployer_version_management(testerchain, test_registry, token_economics):
    deployer = StakingEscrowDeployer(deployer_address=testerchain.etherbase_account,
                                     registry=test_registry,
                                     economics=token_economics)

    untargeted_deployment = deployer.get_latest_enrollment()
    latest_targeted_deployment = deployer.get_principal_contract()

    proxy_deployer = deployer.get_proxy_deployer()
    proxy_target = proxy_deployer.target_contract.address
    assert latest_targeted_deployment.address == proxy_target
    assert untargeted_deployment.address != latest_targeted_deployment.address


def test_manual_proxy_retargeting(testerchain, test_registry, token_economics):

    deployer = StakingEscrowDeployer(registry=test_registry,
                                     deployer_address=testerchain.etherbase_account,
                                     economics=token_economics)

    # Get Proxy-Direct
    proxy_deployer = deployer.get_proxy_deployer()

    # Re-Deploy Staking Escrow
    old_target = proxy_deployer.target_contract.address

    # Get the latest un-targeted contract from the registry
    latest_deployment = deployer.get_latest_enrollment()

    # Build retarget transaction (just for informational purposes)
    transaction = deployer.retarget(target_address=latest_deployment.address,
                                    just_build_transaction=True,
                                    confirmations=0)

    assert transaction['to'] == proxy_deployer.contract.address
    upgrade_function, _params = proxy_deployer.contract.decode_function_input(transaction['data']) # TODO: this only tests for ethtester
    assert upgrade_function.fn_name == proxy_deployer.contract.functions.upgrade.fn_name

    # Retarget, for real
    receipt = deployer.retarget(target_address=latest_deployment.address, confirmations=0)

    assert receipt['status'] == 1

    # Check proxy targets
    new_target = proxy_deployer.contract.functions.target().call()
    assert old_target != new_target
    assert new_target == latest_deployment.address

    # Check address consistency
    new_bare_contract = deployer.get_principal_contract()
    assert new_bare_contract.address == latest_deployment.address == new_target
