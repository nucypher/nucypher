import json
import os

import pytest

from nucypher.blockchain.eth.agents import (
    MultiSigAgent
)
from nucypher.blockchain.eth.registry import LocalContractRegistry
from nucypher.cli.commands.deploy import deploy
from nucypher.utilities.sandbox.constants import (
    TEST_PROVIDER_URI,
)


MULTISIG_THRESHOLD = 4


@pytest.fixture(scope="module")
def multisig_owners(testerchain):
    return tuple(testerchain.unassigned_accounts[0:5])


@pytest.fixture(scope="module")
def multisig_parameters_filepath(multisig_owners, temp_dir_path):
    filepath = os.path.join(temp_dir_path, 'multisig_params.json')

    multisig_parameters = {
        'threshold': MULTISIG_THRESHOLD,
        'owners': list(multisig_owners)
    }

    with open(filepath, 'w') as file:
        file.write(json.dumps(multisig_parameters))

    yield filepath
    if os.path.isfile(filepath):
        os.remove(filepath)


@pytest.fixture(scope="module")
def registry_filepath(temp_dir_path):
    return os.path.join(temp_dir_path, 'nucypher-test-autodeploy.json')


def test_deploy_multisig_contract(click_runner,
                                  multisig_parameters_filepath,
                                  multisig_owners,
                                  registry_filepath):

    #
    # Main
    #

    assert not os.path.exists(registry_filepath), f"Registry File '{registry_filepath}' Exists."
    assert not os.path.lexists(registry_filepath), f"Registry File '{registry_filepath}' Exists."

    command = ['contracts',
               '--registry-outfile', registry_filepath,
               '--provider', TEST_PROVIDER_URI,
               '--poa',
               '--contract-name', 'MultiSig',
               '--parameters', multisig_parameters_filepath]

    user_input = '0\n' + 'Y\n'
    result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    #
    # Agency
    #
    registry = LocalContractRegistry(filepath=registry_filepath)
    agent = MultiSigAgent(registry=registry)

    assert agent.owners == multisig_owners
    assert agent.threshold == MULTISIG_THRESHOLD
    assert agent.nonce == 0



