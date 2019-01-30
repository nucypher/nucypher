import os

import shutil

from nucypher.blockchain.eth.agents import NucypherTokenAgent, MinerAgent
from nucypher.cli.deploy import deploy
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.utilities.sandbox.constants import (
    INSECURE_DEVELOPMENT_PASSWORD,
    TEST_PROVIDER_URI,
    MOCK_REGISTRY_FILEPATH
)


def test_nucypher_deploy_cli_help(custom_filepath, click_runner):

    help_args = ('--help',)
    result = click_runner.invoke(deploy, help_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert "Usage: deploy [OPTIONS] ACTION" in result.output


def test_nucypher_deploy_big_three(click_runner):

    # We start with a blockchain node, and nothign else...
    assert not os.path.isfile(MOCK_REGISTRY_FILEPATH)

    # Deploy the "Big Three"
    try:
        command = ('contracts',
                   '--registry-outfile', MOCK_REGISTRY_FILEPATH,
                   '--provider-uri', TEST_PROVIDER_URI,
                   '--poa'
                   )

        user_input = 'Y\n'+f'{INSECURE_DEVELOPMENT_PASSWORD}\n'*6
        result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
        assert result.exit_code == 0

        # Now show that we can use contract Agency
        token_agent = NucypherTokenAgent()
        assert token_agent.get_balance() == 0  # and read from the blockchain

        miner_agent = MinerAgent()
        assert miner_agent.get_current_period()

        #   ... I changed my ind, destroy the registry!
        destroy_command = ('destroy-registry',
                           '--registry-infile', MOCK_REGISTRY_FILEPATH,
                           '--provider-uri', TEST_PROVIDER_URI,
                           '--poa'
                           )

        user_input = 'Y\n'*2
        result = click_runner.invoke(deploy, destroy_command, input=user_input, catch_exceptions=False)
        assert result.exit_code == 0
        assert MOCK_REGISTRY_FILEPATH in result.output
        assert DEFAULT_CONFIG_ROOT not in result.output, 'WARNING: Deploy CLI tests are using default confg root dir!'
        assert f'Successfully destroyed {MOCK_REGISTRY_FILEPATH}' in result.output
        assert not os.path.isfile(MOCK_REGISTRY_FILEPATH)

    finally:
        # In case of emergency
        shutil.rmtree(MOCK_REGISTRY_FILEPATH, ignore_errors=True)
