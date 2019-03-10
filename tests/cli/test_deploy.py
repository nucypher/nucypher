import os

from nucypher.blockchain.eth.agents import NucypherTokenAgent, MinerAgent, UserEscrowAgent
from nucypher.blockchain.eth.constants import MAX_ALLOWED_LOCKED
from nucypher.blockchain.eth.registry import AllocationRegistry
from nucypher.cli.deploy import deploy
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.utilities.constants import (
    INSECURE_DEVELOPMENT_PASSWORD,
    TEST_PROVIDER_URI,
    MOCK_ALLOCATION_INFILE,
    MOCK_REGISTRY_FILEPATH, MOCK_ALLOCATION_REGISTRY_FILEPATH)


def test_nucypher_deploy_cli_help(testerchain, custom_filepath, click_runner):

    help_args = ('--help',)
    result = click_runner.invoke(deploy, help_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert "Usage: deploy [OPTIONS] ACTION" in result.output
    testerchain.sever_connection()


def test_nucypher_deploy_contracts(testerchain, click_runner, mock_primary_registry_filepath):

    # We start with a blockchain node, and nothing else...
    assert not os.path.isfile(mock_primary_registry_filepath)

    command = ('contracts',
               '--registry-outfile', mock_primary_registry_filepath,
               '--provider-uri', TEST_PROVIDER_URI,
               '--poa')

    user_input = 'Y\n'+f'{INSECURE_DEVELOPMENT_PASSWORD}\n'*6
    result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # Check that the primary contract registry was written
    assert os.path.isfile(mock_primary_registry_filepath)

    # Now show that we can use contract Agency and read from the blockchain
    token_agent = NucypherTokenAgent()
    assert token_agent.get_balance() == 0
    miner_agent = MinerAgent()
    assert miner_agent.get_current_period()
    testerchain.sever_connection()


def test_nucypher_deploy_allocations(testerchain, click_runner, mock_allocation_infile):

    deploy_command = ('allocations',
                      '--registry-infile', MOCK_REGISTRY_FILEPATH,
                      '--allocation-infile', MOCK_ALLOCATION_INFILE,
                      '--allocation-outfile', MOCK_ALLOCATION_REGISTRY_FILEPATH,
                      '--provider-uri', TEST_PROVIDER_URI,
                      '--poa',
                      )

    user_input = 'Y\n'*2
    result = click_runner.invoke(deploy, deploy_command,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    # ensure that a pre-allocation recipient has the allocated token quantity.
    beneficiary = testerchain.interface.w3.eth.accounts[-1]
    allocation_registry = AllocationRegistry(registry_filepath=MOCK_ALLOCATION_REGISTRY_FILEPATH)
    user_escrow_agent = UserEscrowAgent(beneficiary=beneficiary, allocation_registry=allocation_registry)
    assert user_escrow_agent.unvested_tokens == MAX_ALLOWED_LOCKED


def test_destroy_registry(click_runner, mock_primary_registry_filepath):

    #   ... I changed my mind, destroy the registry!
    destroy_command = ('destroy-registry',
                       '--registry-infile', mock_primary_registry_filepath,
                       '--provider-uri', TEST_PROVIDER_URI,
                       '--poa',
                       )

    user_input = 'Y\n'*2
    result = click_runner.invoke(deploy, destroy_command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert mock_primary_registry_filepath in result.output
    assert DEFAULT_CONFIG_ROOT not in result.output, 'WARNING: Deploy CLI tests are using default confg root dir!'
    assert f'Successfully destroyed {mock_primary_registry_filepath}' in result.output
    assert not os.path.isfile(mock_primary_registry_filepath)
