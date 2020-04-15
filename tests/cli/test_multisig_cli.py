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


def test_deploy_multisig_contract(click_runner,
                                  multisig_parameters_filepath,
                                  multisig_owners,
                                  new_local_registry):

    #
    # Main
    #

    command = ['contracts',
               '--registry-infile', new_local_registry.filepath,
               '--provider', TEST_PROVIDER_URI,
               '--contract-name', 'MultiSig',
               '--parameters', multisig_parameters_filepath]

    user_input = '0\n' + 'Y\n'
    result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    #
    # Agency
    #
    registry = LocalContractRegistry(filepath=new_local_registry.filepath)
    agent = MultiSigAgent(registry=registry)

    assert agent.owners == multisig_owners
    assert agent.threshold == MULTISIG_THRESHOLD
    assert agent.nonce == 0



