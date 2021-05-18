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

import json

import os
import pytest

from nucypher.blockchain.eth.agents import (
    MultiSigAgent
)
from nucypher.blockchain.eth.registry import LocalContractRegistry
from nucypher.cli.commands.deploy import deploy
from nucypher.config.constants import TEMPORARY_DOMAIN
from tests.constants import (
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


@pytest.mark.skip("Takes a long time to run; Currently unused.")
def test_deploy_multisig_contract(click_runner,
                                  multisig_parameters_filepath,
                                  multisig_owners,
                                  new_local_registry):

    #
    # Main
    #

    command = ['contracts',
               '--registry-infile', new_local_registry.filepath,
               '--network', TEMPORARY_DOMAIN,
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
