import json
import os
from random import SystemRandom
from string import ascii_uppercase, digits

import pytest
from eth_utils import to_checksum_address

from nucypher.blockchain.eth.agents import (
    NucypherTokenAgent,
    StakingEscrowAgent,
    UserEscrowAgent,
    PolicyManagerAgent,
    AdjudicatorAgent,
    EthereumContractAgent)
from nucypher.blockchain.eth.interfaces import BlockchainInterface, BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import AllocationRegistry
from nucypher.cli.deploy import deploy

from nucypher.utilities.sandbox.constants import (
    TEST_PROVIDER_URI,
    MOCK_REGISTRY_FILEPATH,
    MOCK_ALLOCATION_REGISTRY_FILEPATH
)


def generate_insecure_secret() -> str:
    insecure_secret = ''.join(SystemRandom().choice(ascii_uppercase + digits) for _ in range(16))
    formatted_secret = insecure_secret + '\n'
    return formatted_secret


PLANNED_UPGRADES = 4
INSECURE_SECRETS = {v: generate_insecure_secret() for v in range(1, PLANNED_UPGRADES+1)}


def test_nucypher_deploy_contracts(click_runner,
                                   mock_primary_registry_filepath,
                                   mock_allocation_infile,
                                   token_economics):



    #
    # Setup
    #

    # We start with a blockchain node, and nothing else...
    if os.path.isfile(mock_primary_registry_filepath):
        os.remove(mock_primary_registry_filepath)
    assert not os.path.isfile(mock_primary_registry_filepath)

    #
    # Main
    #

    command = ['contracts',
               '--registry-outfile', mock_primary_registry_filepath,
               '--provider', TEST_PROVIDER_URI,
               '--poa']

    user_input = '0\n' + 'Y\n' + (f'{INSECURE_SECRETS[1]}\n' * 8) + 'DEPLOY'
    result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # Ensure there is a report on each contract
    contract_names = tuple(a.registry_contract_name for a in EthereumContractAgent.__subclasses__())
    for registry_name in contract_names:
        assert registry_name in result.output

    # Check that the primary contract registry was written
    # and peek at some of the registered entries
    assert os.path.isfile(mock_primary_registry_filepath)
    with open(mock_primary_registry_filepath, 'r') as file:

        # Ensure every contract's name was written to the file, somehow
        raw_registry_data = file.read()
        for registry_name in contract_names:
            assert registry_name in raw_registry_data

        # Ensure the Registry is JSON deserializable
        registry_data = json.loads(raw_registry_data)

        # and that is has the correct number of entries
        assert len(registry_data) == 9

        # Read several records
        token_record, escrow_record, dispatcher_record, *other_records = registry_data
        registered_name, registered_address, registered_abi = token_record

    #
    # Agency
    #

    token_agent = NucypherTokenAgent()
    assert token_agent.contract_name == registered_name
    assert token_agent.registry_contract_name == registered_name
    assert token_agent.contract_address == registered_address

    # Now show that we can use contract Agency and read from the blockchain
    assert token_agent.get_balance() == 0
    staking_agent = StakingEscrowAgent()
    assert staking_agent.get_current_period()

    # and at least the others can be instantiated
    assert PolicyManagerAgent()

    # This agent wasn't instantiated before, so we have to supply the blockchain
    blockchain = staking_agent.blockchain
    assert AdjudicatorAgent(blockchain=blockchain)


def test_transfer_tokens(click_runner, mock_primary_registry_filepath):
    #
    # Setup
    #

    # Simulate "Reconnection"
    real_attach_provider = BlockchainDeployerInterface._attach_provider
    cached_blockchain = BlockchainDeployerInterface.reconnect()
    registry = cached_blockchain.registry
    assert registry.filepath == mock_primary_registry_filepath

    def attach_cached_provider(interface, *args, **kwargs):
        cached_provider = cached_blockchain.provider
        real_attach_provider(interface, provider=cached_provider)

    BlockchainDeployerInterface._attach_provider = attach_cached_provider

    # Let's transfer some NU to a random stranger
    recipient_address = to_checksum_address(os.urandom(20))

    token_agent = NucypherTokenAgent()
    assert token_agent.get_balance(address=recipient_address) == 0

    command = ['transfer',
               '--recipient-address', recipient_address,
               '--amount', 42,
               '--registry-infile', mock_primary_registry_filepath,
               '--provider', TEST_PROVIDER_URI,
               '--poa']

    user_input = '0\n' + 'Y\n' + 'Y\n'
    result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # Check that the NU has arrived to the recipient
    assert token_agent.get_balance(address=recipient_address) == 42


def test_upgrade_contracts(click_runner, mock_primary_registry_filepath):

    #
    # Setup
    #

    # Simulate "Reconnection"
    real_attach_provider = BlockchainDeployerInterface._attach_provider
    cached_blockchain = BlockchainDeployerInterface.reconnect()
    registry = cached_blockchain.registry
    assert registry.filepath == mock_primary_registry_filepath

    def attach_cached_provider(interface, *args, **kwargs):
        cached_provider = cached_blockchain.provider
        real_attach_provider(interface, provider=cached_provider)
    BlockchainDeployerInterface._attach_provider = attach_cached_provider

    # Check the existing state of the registry before the meat and potatoes
    expected_enrollments = 9
    with open(mock_primary_registry_filepath, 'r') as file:
        raw_registry_data = file.read()
        registry_data = json.loads(raw_registry_data)
        assert len(registry_data) == expected_enrollments

    #
    # Input Components
    #

    cli_action = 'upgrade'
    base_command = ('--registry-infile', mock_primary_registry_filepath, '--provider', TEST_PROVIDER_URI, '--poa')

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
        #             addr-----secret----new deploy secret (2x for confirmation)
        user_input = '0\n' + yes + old_secret + (new_secret * 2)
        upgrade_inputs[next_version] = user_input

    #
    # Stage Upgrades
    #

    contracts_to_upgrade = ('StakingEscrow',      # v1 -> v2
                            'PolicyManager',      # v1 -> v2
                            'Adjudicator',        # v1 -> v2
                            'UserEscrowProxy',    # v1 -> v2

                            'StakingEscrow',      # v2 -> v3
                            'StakingEscrow',      # v3 -> v4

                            'Adjudicator',        # v2 -> v3
                            'PolicyManager',      # v2 -> v3
                            'UserEscrowProxy',    # v2 -> v3

                            'UserEscrowProxy',    # v3 -> v4
                            'PolicyManager',      # v3 -> v4
                            'Adjudicator',        # v3 -> v4

                            )  # NOTE: Keep all versions the same in this test (all version 4, for example)

    # Each contract starts at version 1
    version_tracker = {name: 1 for name in contracts_to_upgrade}

    #
    # Upgrade Contracts
    #

    for contract_name in contracts_to_upgrade:

        # Select proxy (Dispatcher vs Linker)
        if contract_name == "UserEscrowProxy":
            proxy_name = "UserEscrowLibraryLinker"
        else:
            proxy_name = 'Dispatcher'

        cached_blockchain = BlockchainDeployerInterface.reconnect()
        real_old_contract = cached_blockchain.get_contract_by_name(name=contract_name,
                                                                   proxy_name=proxy_name,
                                                                   use_proxy_address=False)

        # Ensure the proxy targets the current deployed contract
        proxy = cached_blockchain.get_proxy(target_address=real_old_contract.address, proxy_name=proxy_name)
        targeted_address = proxy.functions.target().call()
        assert targeted_address == real_old_contract.address

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
        expected_enrollments += 1

        # Verify the registry is updated (Potatoes)
        with open(mock_primary_registry_filepath, 'r') as file:

            # Read the registry file directly, bypassing its interfaces
            raw_registry_data = file.read()
            registry_data = json.loads(raw_registry_data)
            assert len(registry_data) == expected_enrollments, f'Unexpected number of enrollments for {contract_name}'

            # Check that there is more than one entry, since we've deployed a "version 2"
            expected_contract_enrollments = current_version + 1

            registered_names = [r[0] for r in registry_data]
            contract_enrollments = registered_names.count(contract_name)

            assert contract_enrollments > 1, f"New contract is not enrolled in {MOCK_REGISTRY_FILEPATH}"
            error = f"Incorrect number of records enrolled for {contract_name}. " \
                    f"Expected {expected_contract_enrollments} got {contract_enrollments}."
            assert contract_enrollments == expected_contract_enrollments, error

        # Ensure deployments are different addresses
        cached_blockchain = BlockchainDeployerInterface.reconnect()
        records = cached_blockchain.registry.search(contract_name=contract_name)
        assert len(records) == contract_enrollments, error

        old, new = records[-2:]            # Get the last two entries
        old_name, old_address, *abi = old  # Previous version
        new_name, new_address, *abi = new  # New version

        assert old_address == real_old_contract.address
        assert old_name == new_name        # TODO: Inspect ABI / Move to different test.
        assert old_address != new_address

        # Ensure the proxy now targets the new deployment
        proxy = cached_blockchain.get_proxy(target_address=new_address, proxy_name=proxy_name)
        targeted_address = proxy.functions.target().call()
        assert targeted_address != old_address
        assert targeted_address == new_address


def test_rollback(click_runner, mock_primary_registry_filepath):
    """Roll 'em back!"""

    # Simulate "Reconnection"
    real_attach_provider = BlockchainDeployerInterface._attach_provider
    cached_blockchain = BlockchainDeployerInterface.reconnect()
    registry = cached_blockchain.registry
    assert registry.filepath == mock_primary_registry_filepath

    def attach_cached_provider(interface, *args, **kwargs):
        cached_provider = cached_blockchain.provider
        real_attach_provider(interface, provider=cached_provider)
    BlockchainDeployerInterface._attach_provider = attach_cached_provider

    # Input Components
    yes = 'Y\n'

    # Stage Rollbacks
    old_secret = INSECURE_SECRETS[PLANNED_UPGRADES]
    rollback_secret = generate_insecure_secret()
    user_input = '0\n' + yes + old_secret + rollback_secret + rollback_secret

    contracts_to_rollback = ('StakingEscrow',  # v4 -> v3
                             'PolicyManager',  # v4 -> v3
                             'Adjudicator',    # v4 -> v3
                             )
    # Execute Rollbacks
    for contract_name in contracts_to_rollback:

        command = ('rollback',
                   '--contract-name', contract_name,
                   '--registry-infile', MOCK_REGISTRY_FILEPATH,
                   '--provider', TEST_PROVIDER_URI,
                   '--poa')

        result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
        assert result.exit_code == 0

        blockchain = BlockchainDeployerInterface.reconnect()
        records = blockchain.registry.search(contract_name=contract_name)
        assert len(records) == 4

        *old_records, v3, v4 = records
        current_target, rollback_target = v4, v3

        _name, current_target_address, *abi = current_target
        _name, rollback_target_address, *abi = rollback_target
        assert current_target_address != rollback_target_address

        # Ensure the proxy targets the rollback target (previous version)
        with pytest.raises(BlockchainInterface.UnknownContract):
            blockchain.get_proxy(target_address=current_target_address, proxy_name='Dispatcher')

        proxy = blockchain.get_proxy(target_address=rollback_target_address, proxy_name='Dispatcher')

        # Deeper - Ensure the proxy targets the old deployment on-chain
        targeted_address = proxy.functions.target().call()
        assert targeted_address != current_target
        assert targeted_address == rollback_target_address


def test_nucypher_deploy_allocation_contracts(click_runner,
                                              testerchain,
                                              mock_primary_registry_filepath,
                                              mock_allocation_infile,
                                              token_economics):
    # Simulate "Reconnection"
    real_attach_provider = BlockchainDeployerInterface._attach_provider
    cached_blockchain = BlockchainDeployerInterface.reconnect()
    registry = cached_blockchain.registry
    assert registry.filepath == mock_primary_registry_filepath

    def attach_cached_provider(interface, *args, **kwargs):
        cached_provider = cached_blockchain.provider
        real_attach_provider(interface, provider=cached_provider)
    BlockchainDeployerInterface._attach_provider = attach_cached_provider

    #
    # Main
    #

    deploy_command = ('allocations',
                      '--registry-infile', MOCK_REGISTRY_FILEPATH,
                      '--allocation-infile', mock_allocation_infile.filepath,
                      '--allocation-outfile', MOCK_ALLOCATION_REGISTRY_FILEPATH,
                      '--provider', TEST_PROVIDER_URI,
                      '--poa')

    account_index = '0\n'
    yes = 'Y\n'
    user_input = account_index + yes + yes

    result = click_runner.invoke(deploy,
                                 deploy_command,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    # ensure that a pre-allocation recipient has the allocated token quantity.
    beneficiary = testerchain.client.accounts[-1]
    allocation_registry = AllocationRegistry(registry_filepath=MOCK_ALLOCATION_REGISTRY_FILEPATH)
    user_escrow_agent = UserEscrowAgent(blockchain=cached_blockchain,
                                        beneficiary=beneficiary,
                                        allocation_registry=allocation_registry)
    assert user_escrow_agent.unvested_tokens == token_economics.minimum_allowed_locked

    #
    # Tear Down
    #

    # Destroy existing blockchain
    testerchain.disconnect()
