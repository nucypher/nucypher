

import maya
import pytest
from eth_typing import ChecksumAddress

from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.cli.commands.bond import unbond, bond
from nucypher.cli.literature import UNEXPECTED_HUMAN_OPERATOR, BONDING_TIME, ALREADY_BONDED
from nucypher.config.constants import (
    TEMPORARY_DOMAIN,
    NUCYPHER_ENVVAR_STAKING_PROVIDER_ETH_PASSWORD
)
from nucypher.crypto.powers import TransactingPower
from nucypher.types import StakingProviderInfo
from tests.constants import TEST_ETH_PROVIDER_URI, INSECURE_DEVELOPMENT_PASSWORD

cli_env = {NUCYPHER_ENVVAR_STAKING_PROVIDER_ETH_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}


@pytest.fixture(scope='module', autouse=True)
def mock_transacting_power(module_mocker):
    module_mocker.patch.object(TransactingPower, 'unlock')


@pytest.fixture(scope='module')
def operator_address(mock_testerchain):
    return mock_testerchain.unassigned_accounts[1]


@pytest.fixture(scope='module')
@pytest.mark.usefixtures('test_registry_source_manager', 'mock_contract_agency')
def staking_provider_address(mock_testerchain):
    return mock_testerchain.unassigned_accounts[2]


def test_nucypher_bond_help(click_runner, mock_testerchain):
    command = '--help'
    result = click_runner.invoke(bond, command, catch_exceptions=False)
    assert result.exit_code == 0


def exec_bond(click_runner, operator_address: ChecksumAddress, staking_provider_address: ChecksumAddress):
    command = ('--operator-address', operator_address,
               '--staking-provider', staking_provider_address,
               '--eth-provider', TEST_ETH_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--signer', TEST_ETH_PROVIDER_URI,
               '--force'  # non-interactive only
               )
    result = click_runner.invoke(bond, command, catch_exceptions=False, env=cli_env)
    return result


def exec_unbond(click_runner, staking_provider_address: ChecksumAddress):
    command = ('--staking-provider', staking_provider_address,
               '--eth-provider', TEST_ETH_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--signer', TEST_ETH_PROVIDER_URI,
               '--force'  # non-interactive only
               )
    result = click_runner.invoke(unbond, command, catch_exceptions=False, env=cli_env)
    return result


@pytest.mark.usefixtures('test_registry_source_manager', 'mock_contract_agency', 'patch_keystore')
def test_nucypher_bond_unauthorized(click_runner, mock_testerchain, operator_address, staking_provider_address, mock_application_agent):

    mock_application_agent.is_authorized.return_value = False
    mock_application_agent.get_staking_provider_info.return_value = StakingProviderInfo(
        operator=NULL_ADDRESS,
        operator_confirmed=False,
        operator_start_timestamp=1
    )

    result = exec_bond(
        click_runner=click_runner,
        operator_address=operator_address,
        staking_provider_address=staking_provider_address
    )
    assert result.exit_code == 1
    error_message = f'{staking_provider_address} is not authorized'
    assert error_message in result.output


@pytest.mark.usefixtures('test_registry_source_manager', 'mock_contract_agency', 'test_registry')
def test_nucypher_unexpected_beneficiary(click_runner, mock_testerchain, operator_address, staking_provider_address, mock_application_agent):

    mock_application_agent.get_staking_provider_info.return_value = StakingProviderInfo(
        operator=NULL_ADDRESS,
        operator_confirmed=False,
        operator_start_timestamp=1
    )
    mock_application_agent.get_beneficiary.return_value = mock_testerchain.unassigned_accounts[-1]
    mock_application_agent.get_staking_provider_from_operator.return_value = NULL_ADDRESS

    result = exec_bond(
        click_runner=click_runner,
        operator_address=operator_address,
        staking_provider_address=staking_provider_address
    )

    assert result.exit_code == 1
    assert UNEXPECTED_HUMAN_OPERATOR in result.output


@pytest.mark.usefixtures('test_registry_source_manager', 'mock_contract_agency', 'test_registry')
def test_nucypher_bond(click_runner, mock_testerchain, operator_address, staking_provider_address, mock_application_agent):

    mock_application_agent.get_staking_provider_info.return_value = StakingProviderInfo(
        operator=NULL_ADDRESS,
        operator_confirmed=False,
        operator_start_timestamp=1
    )
    mock_application_agent.get_beneficiary.return_value = NULL_ADDRESS
    mock_application_agent.get_staking_provider_from_operator.return_value = NULL_ADDRESS

    result = exec_bond(
        click_runner=click_runner,
        operator_address=operator_address,
        staking_provider_address=staking_provider_address
    )

    assert result.exit_code == 0


@pytest.mark.usefixtures('test_registry_source_manager', 'mock_contract_agency')
def test_nucypher_unbond_operator(click_runner, mock_testerchain, staking_provider_address, mock_application_agent, operator_address):

    mock_application_agent.get_staking_provider_info.return_value = StakingProviderInfo(
        operator=operator_address,
        operator_confirmed=False,
        operator_start_timestamp=1
    )

    mock_application_agent.get_staking_provider_from_operator.return_value = staking_provider_address

    result = exec_unbond(click_runner=click_runner, staking_provider_address=staking_provider_address)
    assert result.exit_code == 0


@pytest.mark.usefixtures('test_registry_source_manager', 'mock_contract_agency')
def test_nucypher_rebond_too_soon(click_runner, mock_testerchain, operator_address, staking_provider_address, mock_application_agent):

    min_authorized_seconds = 5
    now = mock_testerchain.get_blocktime()
    operator_start_timestamp = now
    termination = operator_start_timestamp + min_authorized_seconds

    mock_application_agent.get_staking_provider_info.return_value = StakingProviderInfo(
        operator=operator_address,
        operator_confirmed=False,
        operator_start_timestamp=operator_start_timestamp
    )
    mock_application_agent.get_min_operator_seconds.return_value = min_authorized_seconds

    result = exec_bond(
        click_runner=click_runner,
        operator_address=operator_address,
        staking_provider_address=staking_provider_address
    )
    assert result.exit_code == 1
    error_message = BONDING_TIME.format(date=maya.MayaDT(termination))
    assert error_message in result.output


@pytest.mark.usefixtures('test_registry_source_manager', 'mock_contract_agency')
def test_nucypher_bond_already_claimed_operator(click_runner, mock_testerchain, operator_address, staking_provider_address, mock_application_agent):
    mock_application_agent.get_staking_provider_info.return_value = StakingProviderInfo(
        operator=NULL_ADDRESS,
        operator_confirmed=False,
        operator_start_timestamp=1
    )
    mock_application_agent.get_beneficiary.return_value = NULL_ADDRESS
    mock_application_agent.get_operator_from_staking_provider.return_value = NULL_ADDRESS
    mock_application_agent.get_staking_provider_from_operator.return_value = mock_testerchain.unassigned_accounts[4]

    result = exec_bond(
        click_runner=click_runner,
        operator_address=operator_address,
        staking_provider_address=staking_provider_address
    )
    assert result.exit_code == 1


@pytest.mark.usefixtures('test_registry_source_manager', 'mock_contract_agency')
def test_nucypher_rebond_operator(click_runner, mock_testerchain, operator_address, staking_provider_address, mock_application_agent):
    mock_application_agent.get_staking_provider_info.return_value = StakingProviderInfo(
        operator=mock_testerchain.unassigned_accounts[-1],
        operator_confirmed=False,
        operator_start_timestamp=1
    )
    mock_application_agent.get_beneficiary.return_value = NULL_ADDRESS
    mock_application_agent.get_staking_provider_from_operator.return_value = NULL_ADDRESS

    result = exec_bond(
        click_runner=click_runner,
        operator_address=operator_address,
        staking_provider_address=staking_provider_address
    )
    assert result.exit_code == 0
