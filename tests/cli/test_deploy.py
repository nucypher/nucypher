import json
import os
from random import SystemRandom
from string import ascii_uppercase, digits

import pytest

from nucypher.blockchain.eth.actors import Deployer
from nucypher.blockchain.eth.agents import (
    NucypherTokenAgent,
    MinerAgent,
    UserEscrowAgent,
    PolicyAgent,
    MiningAdjudicatorAgent
)
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.registry import AllocationRegistry, EthereumContractRegistry
from nucypher.cli.deploy import deploy
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.utilities.sandbox.constants import (
    TEST_PROVIDER_URI,
    MOCK_ALLOCATION_INFILE,
    MOCK_REGISTRY_FILEPATH, MOCK_ALLOCATION_REGISTRY_FILEPATH
)


def generate_insecure_secret() -> str:
    insecure_secret = ''.join(SystemRandom().choice(ascii_uppercase + digits) for _ in range(16))
    formatted_secret = insecure_secret + '\n'
    return formatted_secret


PLANNED_UPGRADES = 4
INSECURE_SECRETS = {v: generate_insecure_secret() for v in range(1, PLANNED_UPGRADES+1)}


def test_nucypher_deploy_all_contracts(testerchain, click_runner, mock_primary_registry_filepath):

    # We start with a blockchain node, and nothing else...
    assert not os.path.isfile(mock_primary_registry_filepath)

    command = ('deploy',
               '--registry-outfile', mock_primary_registry_filepath,
               '--provider-uri', TEST_PROVIDER_URI,
               '--poa')

    user_input = 'Y\n' + (f'{INSECURE_SECRETS[1]}\n' * 8)
    result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # Ensure there is a report on each contract
    for registry_name in Deployer.contract_names:
        assert registry_name in result.output

    # Check that the primary contract registry was written
    # and peek at some of the registered entries
    assert os.path.isfile(mock_primary_registry_filepath)
    with open(mock_primary_registry_filepath, 'r') as file:

        # Ensure every contract's name was written to the file, somehow
        raw_registry_data = file.read()
        for registry_name in Deployer.contract_names:
            assert registry_name in raw_registry_data

        # Ensure the Registry is JSON deserializable
        registry_data = json.loads(raw_registry_data)

        # and that is has the correct number of entries
        assert len(registry_data) == 9

        # Read several records
        token_record, escrow_record, dispatcher_record, *other_records = registry_data
        registered_name, registered_address, registered_abi = token_record
        token_agent = NucypherTokenAgent()
        assert token_agent.contract_name == registered_name
        assert token_agent.registry_contract_name == registered_name
        assert token_agent.contract_address == registered_address

    # Now show that we can use contract Agency and read from the blockchain
    assert token_agent.get_balance() == 0
    miner_agent = MinerAgent()
    assert miner_agent.get_current_period()

    # and at least the others can be instantiated
    assert PolicyAgent()
    assert MiningAdjudicatorAgent()
    testerchain.sever_connection()


def test_upgrade_contracts(click_runner):
    contracts_to_upgrade = ('MinersEscrow',  # Initial upgrades (version 2)
                            'PolicyManager',
                            'MiningAdjudicator',
                            'UserEscrowProxy',

    #
    # Setup
    #

    # Connect to the blockchain with a blank temporary file-based registry
    mock_temporary_registry = EthereumContractRegistry(registry_filepath=MOCK_REGISTRY_FILEPATH)
    blockchain = Blockchain.connect(registry=mock_temporary_registry)

    # Check the existing state of the registry before the meat and potatoes
    expected_registrations = 9
    with open(MOCK_REGISTRY_FILEPATH, 'r') as file:
        raw_registry_data = file.read()
        registry_data = json.loads(raw_registry_data)
        assert len(registry_data) == expected_registrations

    #
    # Input Components
    #

    cli_action = 'upgrade'
    base_command = ('--registry-infile', MOCK_REGISTRY_FILEPATH, '--provider-uri', TEST_PROVIDER_URI, '--poa')

    # Generate user inputs
    yes = 'Y\n'  # :-)
    upgrade_inputs = dict()
    for version, insecure_secret in INSECURE_SECRETS.items():

        next_version = version + 1
        old_secret = INSECURE_SECRETS[version]
        try:
            new_secret = INSECURE_SECRETS[next_version]
        except KeyError:
            continue

        user_input = yes + old_secret + (new_secret * 2)  # twice for confirmation prompt
        upgrade_inputs[next_version] = user_input

    #
    # Stage Upgrades
    #

    contracts_to_upgrade = ('MinersEscrow',       # v1 -> v2
                            'PolicyManager',      # v1 -> v2
                            'MiningAdjudicator',  # v1 -> v2
                            'UserEscrowProxy',    # v1 -> v2

                            'MinersEscrow',       # v2 -> v3
                            'MinersEscrow',       # v3 -> v4

                            'MiningAdjudicator',  # v2 -> v3
                            'PolicyManager',      # v2 -> v3
                            'UserEscrowProxy',    # v2 -> v3

                            'UserEscrowProxy',    # v3 -> v4
                            'PolicyManager',      # v3 -> v4
                            'MiningAdjudicator',  # v3 -> v4

                            )  # NOTE: Keep all versions the same in this test (all version 4, for example)

    # Each contract starts at version 1
    version_tracker = {name: 1 for name in contracts_to_upgrade}

    #
    # Upgrade Contracts
    #

    for contract_name in contracts_to_upgrade:

        # Assemble CLI command
        command = (cli_action, '--contract-name', contract_name, *base_command)

        # Select upgrade interactive input scenario
        current_version = version_tracker[contract_name]
        new_version = current_version + 1
        user_input = upgrade_inputs[new_version]

        # Execute upgrade (Meat)
        result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
        assert result.exit_code == 0  # TODO: Console painting

        # Mutate the version tracking
        version_tracker[contract_name] += 1
        expected_registrations += 1

        # Verify the registry is updated (Potatoes)
        with open(MOCK_REGISTRY_FILEPATH, 'r') as file:

            # Read the registry file directly, bypassing its interfaces
            raw_registry_data = file.read()
            registry_data = json.loads(raw_registry_data)
            assert len(registry_data) == expected_registrations

            # Check that there is more than one entry, since we've deployed a "version 2"
            expected_enrollments = current_version + 1

            registered_names = [r[0] for r in registry_data]
            enrollments = registered_names.count(contract_name)

            assert enrollments > 1, f"New contract is not enrolled in {MOCK_REGISTRY_FILEPATH}"
            assert enrollments == expected_enrollments, f"Incorrect number of records enrolled for {contract_name}. " \
                                                        f"Expected {expected_enrollments} got {enrollments}."

        # Ensure deployments are different addresses
        records = blockchain.interface.registry.search(contract_name=contract_name)
        assert len(records) == expected_enrollments

        old, new = records[-2:]            # Get the last two entries
        old_name, old_address, *abi = old  # Previous version
        new_name, new_address, *abi = new  # New version
        assert old_name == new_name        # TODO: Inspect ABI?
        assert old_address != new_address

        # Select proxy (Dispatcher vs Linker)
        if contract_name == "UserEscrowProxy":
            proxy_name = "UserEscrowLibraryLinker"
        else:
            proxy_name = 'Dispatcher'

        # Ensure the proxy targets the new deployment
        proxy = blockchain.interface.get_proxy(target_address=new_address, proxy_name=proxy_name)
        targeted_address = proxy.functions.target().call()
        assert targeted_address != old_address
        assert targeted_address == new_address


def test_rollback(click_runner):
    """Roll 'em all back!"""

    mock_temporary_registry = EthereumContractRegistry(registry_filepath=MOCK_REGISTRY_FILEPATH)
    blockchain = Blockchain.connect(registry=mock_temporary_registry)

    # Input Components
    yes = 'Y\n'

    # Stage Rollbacks
    old_secret = INSECURE_SECRETS[PLANNED_UPGRADES]
    rollback_secret = generate_insecure_secret()
    user_input = yes + old_secret + rollback_secret + rollback_secret

    contracts_to_rollback = ('MinersEscrow',       # v4 -> v3
                             'PolicyManager',      # v4 -> v3
                             'MiningAdjudicator',  # v4 -> v3
                             # 'UserEscrowProxy'     # v4 -> v3  # TODO: Rollback support for UserEscrowProxy
                             )
    # Execute Rollbacks
    for contract_name in contracts_to_rollback:

        command = ('rollback',
                   '--contract-name', contract_name,
                   '--registry-infile', MOCK_REGISTRY_FILEPATH,
                   '--provider-uri', TEST_PROVIDER_URI,
                   '--poa')

        result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
        assert result.exit_code == 0

        records = blockchain.interface.registry.search(contract_name=contract_name)
        assert len(records) == 4

        *old_records, v3, v4 = records
        current_target, rollback_target = v4, v3

        _name, current_target_address, *abi = current_target
        _name, rollback_target_address, *abi = rollback_target
        assert current_target_address != rollback_target_address

        # Select proxy (Dispatcher vs Linker)
        if contract_name == "UserEscrowProxy":
            proxy_name = "UserEscrowLibraryLinker"
        else:
            proxy_name = 'Dispatcher'

        # Ensure the proxy targets the rollback target (previous version)
        with pytest.raises(BlockchainInterface.UnknownContract):
            blockchain.interface.get_proxy(target_address=current_target_address, proxy_name=proxy_name)

        proxy = blockchain.interface.get_proxy(target_address=rollback_target_address, proxy_name=proxy_name)

        # Deeper - Ensure the proxy targets the old deployment on-chain
        targeted_address = proxy.functions.target().call()
        assert targeted_address != current_target
        assert targeted_address == rollback_target_address

    command = ('contracts',
               '--upgrade',
               '--contract-name', 'PolicyManager',
               '--registry-infile', MOCK_REGISTRY_FILEPATH,
               '--provider-uri', TEST_PROVIDER_URI,
               '--poa')

    # Stage Rollbacks
    old_secret = INSECURE_SECRETS[PLANNED_UPGRADES]
    rollback_secret = generate_insecure_secret()
    user_input = yes + old_secret + rollback_secret + rollback_secret

    contracts_to_rollback = ('MinersEscrow',       # v4 -> v3
                             'PolicyManager',      # v4 -> v3
                             'MiningAdjudicator',  # v4 -> v3
                             # 'UserEscrowProxy'     # v4 -> v3  # TODO
                             )
    # Execute Rollbacks
    for contract_name in contracts_to_rollback:

        command = ('rollback',
                   '--contract-name', contract_name,
                   '--registry-infile', MOCK_REGISTRY_FILEPATH,
                   '--provider-uri', TEST_PROVIDER_URI,
                   '--poa')

        result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
        assert result.exit_code == 0

        records = blockchain.interface.registry.search(contract_name=contract_name)
        assert len(records) == 4

        *old_records, v3, v4 = records
        current_target, rollback_target = v4, v3

        _name, current_target_address, *abi = current_target
        _name, rollback_target_address, *abi = rollback_target
        assert current_target_address != rollback_target_address

        # Select proxy (Dispatcher vs Linker)
        if contract_name == "UserEscrowProxy":
            proxy_name = "UserEscrowLibraryLinker"
        else:
            proxy_name = 'Dispatcher'

        # Ensure the proxy targets the rollback target (previous version)
        with pytest.raises(BlockchainInterface.UnknownContract):
            blockchain.interface.get_proxy(target_address=current_target_address, proxy_name=proxy_name)

        proxy = blockchain.interface.get_proxy(target_address=rollback_target_address, proxy_name=proxy_name)

        # Deeper - Ensure the proxy targets the old deployment on-chain
        targeted_address = proxy.functions.target().call()
        assert targeted_address != current_target
        assert targeted_address == rollback_target_address


def test_nucypher_deploy_allocations(testerchain, click_runner, mock_allocation_infile, token_economics):

    deploy_command = ('allocations',
                      '--registry-infile', MOCK_REGISTRY_FILEPATH,
                      '--allocation-infile', MOCK_ALLOCATION_INFILE,
                      '--allocation-outfile', MOCK_ALLOCATION_REGISTRY_FILEPATH,
                      '--provider-uri', TEST_PROVIDER_URI,
                      '--poa')

    user_input = 'Y\n'*2
    result = click_runner.invoke(deploy, deploy_command,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    # ensure that a pre-allocation recipient has the allocated token quantity.
    beneficiary = testerchain.interface.w3.eth.accounts[-1]
    allocation_registry = AllocationRegistry(registry_filepath=MOCK_ALLOCATION_REGISTRY_FILEPATH)
    user_escrow_agent = UserEscrowAgent(beneficiary=beneficiary, allocation_registry=allocation_registry)
    assert user_escrow_agent.unvested_tokens == token_economics.maximum_allowed_locked


def test_destroy_registry(click_runner, mock_primary_registry_filepath):

    #   ... I changed my mind, destroy the registry!
    destroy_command = ('destroy-registry',
                       '--registry-infile', mock_primary_registry_filepath,
                       '--provider-uri', TEST_PROVIDER_URI,
                       '--poa')

    user_input = 'Y\n'*2
    result = click_runner.invoke(deploy, destroy_command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert mock_primary_registry_filepath in result.output
    assert DEFAULT_CONFIG_ROOT not in result.output, 'WARNING: Deploy CLI tests are using default config root dir!'
    assert f'Successfully destroyed {mock_primary_registry_filepath}' in result.output
    assert not os.path.isfile(mock_primary_registry_filepath)
