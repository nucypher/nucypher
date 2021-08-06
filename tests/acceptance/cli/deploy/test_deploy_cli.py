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
from pathlib import Path
from unittest.mock import patch, PropertyMock

import pytest

from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.registry import LocalContractRegistry
from nucypher.blockchain.eth.signers import Signer
from nucypher.blockchain.eth.sol import SOLIDITY_COMPILER_VERSION
from nucypher.cli.commands.deploy import deploy
from nucypher.config.constants import TEMPORARY_DOMAIN
from tests.constants import TEST_PROVIDER_URI, YES_ENTER

PLANNED_UPGRADES = 4
CONTRACTS_TO_UPGRADE = ('StakingEscrow', 'PolicyManager', 'Adjudicator', 'StakingInterface')


@pytest.fixture(scope="module")
def registry_filepath(temp_dir_path: Path):
    return temp_dir_path / 'nucypher-test-autodeploy.json'


def test_deploy_single_contract(click_runner, tempfile_path):

    # Perform the Test
    command = ['contracts',
               '--contract-name', NucypherTokenAgent.contract_name,
               '--registry-infile', str(tempfile_path.absolute()),
               '--provider', TEST_PROVIDER_URI,
               '--signer', TEST_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--debug']

    user_input = '0\n' + YES_ENTER + 'DEPLOY'
    result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0, result.output


def test_deploy_signer_uri_testnet_check(click_runner, mocker, tempfile_path):
    spy_from_signer_uri = mocker.spy(Signer, 'from_signer_uri')

    with patch('nucypher.blockchain.eth.actors.BaseActor.eth_balance', PropertyMock(return_value=0)):
        command = ['contracts',
                   '--contract-name', NucypherTokenAgent.contract_name,
                   '--registry-infile', str(tempfile_path.absolute()),
                   '--provider', TEST_PROVIDER_URI,
                   '--signer', TEST_PROVIDER_URI,
                   '--network', TEMPORARY_DOMAIN,
                   '--debug']

        user_input = '0\n' + YES_ENTER + 'DEPLOY'

        # fail trying to deploy contract to testnet since ETH balance is 0, signer will already have been initialized
        result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
        assert result.exit_code != 0, result.output  # expected failure given eth balance is 0
        spy_from_signer_uri.assert_called_with(TEST_PROVIDER_URI, testnet=True)

        # fail trying to deploy contract to mainnet (:-o) since ETH balance is 0, signer will already have been initialized
        with patch('nucypher.blockchain.eth.clients.EthereumTesterClient.chain_name', PropertyMock(return_value='Mainnet')):
            result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
            assert result.exit_code != 0, result.output  # expected failure given invalid contract name
            spy_from_signer_uri.assert_called_with(TEST_PROVIDER_URI, testnet=False)  # the "real" deal


def test_upgrade_contracts(click_runner, test_registry_source_manager, test_registry,
                           testerchain, registry_filepath, agency):

    NetworksInventory.DEFAULT = TEMPORARY_DOMAIN
    registry_filepath = test_registry.commit(filepath=registry_filepath)

    #
    # Setup
    #

    # Check the existing state of the registry before the meat and potatoes
    expected_enrollments = 11
    with open(registry_filepath, 'r') as file:
        raw_registry_data = file.read()
        registry_data = json.loads(raw_registry_data)
        assert len(registry_data) == expected_enrollments

    #
    # Input Components
    #

    cli_action = 'upgrade'
    base_command = ('--registry-infile', str(registry_filepath.absolute()),
                    '--provider', TEST_PROVIDER_URI,
                    '--signer', TEST_PROVIDER_URI,
                    '--confirmations', 1,
                    '--network', TEMPORARY_DOMAIN,
                    '--force'  # skip registry preflight check for tests
                    )

    #
    # Stage Upgrades
    #

    contracts_to_upgrade = ('StakingEscrow',      # v1 -> v2
                            'PolicyManager',      # v1 -> v2
                            'Adjudicator',        # v1 -> v2
                            'StakingInterface',   # v1 -> v2

                            'StakingEscrow',      # v2 -> v3
                            'StakingEscrow',      # v3 -> v4

                            'Adjudicator',        # v2 -> v3
                            'PolicyManager',      # v2 -> v3
                            'StakingInterface',   # v2 -> v3

                            'StakingInterface',   # v3 -> v4
                            'PolicyManager',      # v3 -> v4
                            'Adjudicator',        # v3 -> v4

                            )  # NOTE: Keep all versions the same in this test (all version 4, for example)

    # Each contract starts at version 1
    version_tracker = {name: 1 for name in CONTRACTS_TO_UPGRADE}

    #
    # Upgrade Contracts
    #

    for contract_name in contracts_to_upgrade:

        # Select proxy (Dispatcher vs Router)
        if contract_name == "StakingInterface":
            proxy_name = "StakingInterfaceRouter"
        else:
            proxy_name = 'Dispatcher'

        registry = LocalContractRegistry(filepath=registry_filepath)
        real_old_contract = testerchain.get_contract_by_name(contract_name=contract_name,
                                                             registry=registry,
                                                             proxy_name=proxy_name,
                                                             use_proxy_address=False)

        # Ensure the proxy targets the current deployed contract
        proxy = testerchain.get_proxy_contract(registry=registry,
                                               target_address=real_old_contract.address,
                                               proxy_name=proxy_name)
        targeted_address = proxy.functions.target().call()
        assert targeted_address == real_old_contract.address

        # Assemble CLI command
        command = (cli_action, '--contract-name', contract_name, '--ignore-deployed', *base_command)

        # Select upgrade interactive input scenario
        current_version = version_tracker[contract_name]
        user_input = '0\n' + YES_ENTER + YES_ENTER + YES_ENTER

        # Execute upgrade (Meat)
        result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
        assert result.exit_code == 0, result.output
        assert "Successfully deployed" in result.output

        # Mutate the version tracking
        version_tracker[contract_name] += 1
        expected_enrollments += 1

        # Verify the registry is updated (Potatoes)
        with open(registry_filepath, 'r') as file:

            # Read the registry file directly, bypassing its interfaces
            raw_registry_data = file.read()
            registry_data = json.loads(raw_registry_data)
            assert len(registry_data) == expected_enrollments, f'Unexpected number of enrollments for {contract_name}'

            # Check that there is more than one entry, since we've deployed a "version 2"
            expected_contract_enrollments = current_version + 1

            registered_names = [r[0] for r in registry_data]
            contract_enrollments = registered_names.count(contract_name)

            assert contract_enrollments > 1, f"New contract is not enrolled in {registry_filepath}"
            error = f"Incorrect number of records enrolled for {contract_name}. " \
                    f"Expected {expected_contract_enrollments} got {contract_enrollments}."
            assert contract_enrollments == expected_contract_enrollments, error

        # Ensure deployments are different addresses
        registry = LocalContractRegistry(filepath=registry_filepath)
        records = registry.search(contract_name=contract_name)
        assert len(records) == contract_enrollments, error

        old, new = records[-2:]            # Get the last two entries
        old_name, _old_version, old_address, *abi = old  # Previous version
        new_name, _new_version, new_address, *abi = new  # New version

        assert old_address == real_old_contract.address
        assert old_name == new_name        # TODO: Inspect ABI / Move to different test.
        assert old_address != new_address

        # Ensure the proxy now targets the new deployment
        proxy = testerchain.get_proxy_contract(registry=registry,
                                               target_address=new_address,
                                               proxy_name=proxy_name)
        targeted_address = proxy.functions.target().call()
        assert targeted_address != old_address
        assert targeted_address == new_address


def test_rollback(click_runner, testerchain, registry_filepath, agency):
    """Roll 'em back!"""

    # Stage Rollbacks
    contracts_to_rollback = ('StakingEscrow',  # v4 -> v3
                             'PolicyManager',  # v4 -> v3
                             'Adjudicator',    # v4 -> v3
                             )

    # Execute Rollbacks
    for contract_name in contracts_to_rollback:

        command = ('rollback',
                   '--contract-name', contract_name,
                   '--registry-infile', str(registry_filepath.absolute()),
                   '--network', TEMPORARY_DOMAIN,
                   '--provider', TEST_PROVIDER_URI,
                   '--signer', TEST_PROVIDER_URI
                   )

        user_input = '0\n' + YES_ENTER
        result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
        assert result.exit_code == 0, result.output

        # TODO unify this, trust more to registry_filepath, reduce calls
        registry = LocalContractRegistry(filepath=registry_filepath)
        records = registry.search(contract_name=contract_name)
        assert len(records) == 4

        *old_records, v3, v4 = records
        current_target, rollback_target = v4, v3

        _name, _version, current_target_address, *abi = current_target
        _name, _version, rollback_target_address, *abi = rollback_target
        assert current_target_address != rollback_target_address

        # Ensure the proxy targets the rollback target (previous version)
        with pytest.raises(BlockchainInterface.UnknownContract):
            testerchain.get_proxy_contract(registry=registry,
                                           target_address=current_target_address,
                                           proxy_name='Dispatcher')

        proxy = testerchain.get_proxy_contract(registry=registry,
                                               target_address=rollback_target_address,
                                               proxy_name='Dispatcher')

        # Deeper - Ensure the proxy targets the old deployment on-chain
        targeted_address = proxy.functions.target().call()
        assert targeted_address != current_target
        assert targeted_address == rollback_target_address
