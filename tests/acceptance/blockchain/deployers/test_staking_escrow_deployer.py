


import pytest
from constant_sorrow import constants
from constant_sorrow.constants import BARE

from nucypher.blockchain.eth.deployers import (DispatcherDeployer, StakingEscrowDeployer)


@pytest.fixture()
def staking_escrow_deployer(testerchain, threshold_staking, application_economics, test_registry,
                            deployment_progress, transacting_power):
    deployer = StakingEscrowDeployer(
        staking_interface=threshold_staking.address,
        economics=application_economics,
        registry=test_registry
    )
    deployer.deploy(
        progress=deployment_progress,
        deployment_mode=constants.INIT,
        transacting_power=transacting_power
    )
    return deployer


@pytest.mark.usefixtures('testerchain', 'agency', 'test_registry')
def test_staking_escrow_deployment(staking_escrow_deployer, deployment_progress, transacting_power):
    deployment_receipts = staking_escrow_deployer.deploy(progress=deployment_progress,
                                                         deployment_mode=constants.FULL,
                                                         transacting_power=transacting_power)

    # deployment steps must match expected number of steps
    # assert deployment_progress.num_steps == len(staking_escrow_deployer.deployment_steps) == len(deployment_receipts) == 2

    for step in staking_escrow_deployer.deployment_steps:
        assert deployment_receipts[step]['status'] == 1


@pytest.mark.skip
def test_staking_escrow_has_dispatcher(testerchain, test_registry, transacting_power):

    # Let's get the "bare" StakingEscrow contract (i.e., unwrapped, no dispatcher)
    existing_bare_contract = testerchain.get_contract_by_name(registry=test_registry,
                                                              contract_name=StakingEscrowDeployer.contract_name,
                                                              proxy_name=DispatcherDeployer.contract_name,
                                                              use_proxy_address=False)

    # This contract shouldn't be accessible directly through the deployer or the agent
    assert staking_escrow_deployer.contract_address != existing_bare_contract.address

    # The wrapped contract, on the other hand, points to the bare one.
    target = staking_escrow_deployer.contract.functions.target().call()
    assert target == existing_bare_contract.address


def test_upgrade(testerchain, test_registry, application_economics, transacting_power, threshold_staking):

    deployer = StakingEscrowDeployer(staking_interface=threshold_staking.address,
                                     registry=test_registry,
                                     economics=application_economics)

    receipts = deployer.upgrade(ignore_deployed=True, confirmations=0, transacting_power=transacting_power)
    for title, receipt in receipts.items():
        assert receipt['status'] == 1


def test_rollback(testerchain, test_registry, transacting_power, threshold_staking):

    deployer = StakingEscrowDeployer(staking_interface=threshold_staking.address, registry=test_registry)

    contract = testerchain.get_contract_by_name(registry=test_registry,
                                                contract_name=deployer.contract_name,
                                                proxy_name=DispatcherDeployer.contract_name,
                                                use_proxy_address=True)

    current_target = contract.functions.target().call()

    # Let's do one more upgrade
    receipts = deployer.upgrade(ignore_deployed=True, confirmations=0, transacting_power=transacting_power)

    for title, receipt in receipts.items():
        assert receipt['status'] == 1

    old_target = current_target
    current_target = contract.functions.target().call()
    assert current_target != old_target

    # It's time to rollback.
    receipt = deployer.rollback(transacting_power=transacting_power)
    assert receipt['status'] == 1

    new_target = contract.functions.target().call()
    assert new_target != current_target
    assert new_target == old_target


def test_deploy_bare_upgradeable_contract_deployment(testerchain,
                                                     test_registry,
                                                     application_economics,
                                                     transacting_power,
                                                     threshold_staking):
    deployer = StakingEscrowDeployer(staking_interface=threshold_staking.address,
                                     registry=test_registry,
                                     economics=application_economics)

    enrolled_names = list(test_registry.enrolled_names)
    old_number_of_enrollments = enrolled_names.count(StakingEscrowDeployer.contract_name)
    old_number_of_proxy_enrollments = enrolled_names.count(StakingEscrowDeployer._proxy_deployer.contract_name)

    receipts = deployer.deploy(deployment_mode=BARE, ignore_deployed=True, transacting_power=transacting_power)
    for title, receipt in receipts.items():
        assert receipt['status'] == 1

    enrolled_names = list(test_registry.enrolled_names)
    new_number_of_enrollments = enrolled_names.count(StakingEscrowDeployer.contract_name)
    new_number_of_proxy_enrollments = enrolled_names.count(StakingEscrowDeployer._proxy_deployer.contract_name)

    # The principal contract was deployed.
    assert new_number_of_enrollments == (old_number_of_enrollments + 1)

    # The Dispatcher was not deployed.
    assert new_number_of_proxy_enrollments == old_number_of_proxy_enrollments


def test_deployer_version_management(testerchain, test_registry, application_economics):
    deployer = StakingEscrowDeployer(registry=test_registry, economics=application_economics)

    untargeted_deployment = deployer.get_latest_enrollment()
    latest_targeted_deployment = deployer.get_principal_contract()

    proxy_deployer = deployer.get_proxy_deployer()
    proxy_target = proxy_deployer.target_contract.address
    assert latest_targeted_deployment.address == proxy_target
    assert untargeted_deployment.address != latest_targeted_deployment.address


def test_manual_proxy_retargeting(testerchain, test_registry, application_economics, transacting_power):

    deployer = StakingEscrowDeployer(registry=test_registry, economics=application_economics)

    # Get Proxy-Direct
    proxy_deployer = deployer.get_proxy_deployer()

    # Re-Deploy Staking Escrow
    old_target = proxy_deployer.target_contract.address

    # Get the latest un-targeted contract from the registry
    latest_deployment = deployer.get_latest_enrollment()

    # Build retarget transaction (just for informational purposes)
    transaction = deployer.retarget(transacting_power=transacting_power,
                                    target_address=latest_deployment.address,
                                    just_build_transaction=True,
                                    confirmations=0)

    assert transaction['to'] == proxy_deployer.contract.address
    upgrade_function, _params = proxy_deployer.contract.decode_function_input(transaction['data'])  # TODO: this only tests for ethtester
    assert upgrade_function.fn_name == proxy_deployer.contract.functions.upgrade.fn_name

    # Retarget, for real
    receipt = deployer.retarget(transacting_power=transacting_power,
                                target_address=latest_deployment.address,
                                confirmations=0)

    assert receipt['status'] == 1

    # Check proxy targets
    new_target = proxy_deployer.contract.functions.target().call()
    assert old_target != new_target
    assert new_target == latest_deployment.address

    # Check address consistency
    new_bare_contract = deployer.get_principal_contract()
    assert new_bare_contract.address == latest_deployment.address == new_target
