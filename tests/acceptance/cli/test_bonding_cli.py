

import pytest
from eth_typing import ChecksumAddress

from nucypher.cli.commands.bond import bond, unbond
from nucypher.config.constants import TEMPORARY_DOMAIN
from tests.constants import TEST_ETH_PROVIDER_URI, INSECURE_DEVELOPMENT_PASSWORD


@pytest.fixture(scope='module')
def operator_address(testerchain):
    return testerchain.unassigned_accounts.pop(1)


@pytest.fixture(scope='module')
@pytest.mark.usefixtures('test_registry_source_manager')
def staking_provider_address(testerchain):
    return testerchain.unassigned_accounts.pop(1)


def test_nucypher_bond_help(click_runner, testerchain):
    command = '--help'
    result = click_runner.invoke(bond, command, catch_exceptions=False)
    assert result.exit_code == 0


@pytest.fixture(scope='module')
def authorized_staking_provider(testerchain, threshold_staking, staking_provider_address, application_economics):
    # initialize threshold stake
    tx = threshold_staking.functions.setRoles(staking_provider_address).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.authorizationIncreased(staking_provider_address, 0, application_economics.min_authorization).transact()
    testerchain.wait_for_receipt(tx)
    return staking_provider_address


def exec_bond(click_runner, operator_address: ChecksumAddress, staking_provider_address: ChecksumAddress):
    command = ('--operator-address', operator_address,
               '--staking-provider', staking_provider_address,
               '--eth-provider', TEST_ETH_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--signer', TEST_ETH_PROVIDER_URI,
               '--force')
    result = click_runner.invoke(bond,
                                 command,
                                 catch_exceptions=False,
                                 env=dict(NUCYPHER_STAKING_PROVIDER_ETH_PASSWORD=INSECURE_DEVELOPMENT_PASSWORD))
    return result


def exec_unbond(click_runner, staking_provider_address: ChecksumAddress):
    command = ('--staking-provider', staking_provider_address,
               '--eth-provider', TEST_ETH_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--signer', TEST_ETH_PROVIDER_URI,
               '--force')
    result = click_runner.invoke(unbond,
                                 command,
                                 catch_exceptions=False,
                                 env=dict(NUCYPHER_STAKING_PROVIDER_ETH_PASSWORD=INSECURE_DEVELOPMENT_PASSWORD))
    return result


@pytest.mark.usefixtures('test_registry_source_manager')
def test_nucypher_bond_unauthorized(click_runner, testerchain, operator_address, staking_provider_address):
    result = exec_bond(
        click_runner=click_runner,
        operator_address=operator_address,
        staking_provider_address=staking_provider_address
    )
    assert result.exit_code == 1
    error_message = f'{staking_provider_address} is not authorized'
    assert error_message in result.output


@pytest.mark.usefixtures('test_registry_source_manager', 'test_registry')
def test_nucypher_bond(click_runner, testerchain, operator_address, authorized_staking_provider):
    result = exec_bond(
        click_runner=click_runner,
        operator_address=operator_address,
        staking_provider_address=authorized_staking_provider
    )
    assert result.exit_code == 0


@pytest.mark.usefixtures('test_registry_source_manager')
def test_nucypher_rebond_too_soon(click_runner, testerchain, operator_address, staking_provider_address):
    result = exec_bond(
        click_runner=click_runner,
        operator_address=operator_address,
        staking_provider_address=staking_provider_address
    )
    assert result.exit_code == 1
    error_message = 'Bonding/Unbonding not permitted until '
    assert error_message in result.output


@pytest.mark.usefixtures('test_registry_source_manager')
def test_nucypher_rebond_operator(click_runner,
                                  testerchain,
                                  operator_address,
                                  staking_provider_address,
                                  application_economics):
    testerchain.time_travel(seconds=application_economics.min_operator_seconds)
    result = exec_bond(
        click_runner=click_runner,
        operator_address=testerchain.unassigned_accounts[-1],
        staking_provider_address=staking_provider_address
    )
    assert result.exit_code == 0


@pytest.mark.usefixtures('test_registry_source_manager')
def test_nucypher_unbond_operator(click_runner,
                                  testerchain,
                                  staking_provider_address,
                                  application_economics):
    testerchain.time_travel(seconds=application_economics.min_operator_seconds)
    result = exec_unbond(click_runner=click_runner, staking_provider_address=staking_provider_address)
    assert result.exit_code == 0
