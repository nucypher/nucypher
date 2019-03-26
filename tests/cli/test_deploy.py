import json
import os

from nucypher.blockchain.eth.actors import Deployer
from nucypher.blockchain.eth.agents import (
    NucypherTokenAgent,
    MinerAgent,
    UserEscrowAgent,
    PolicyAgent,
    MiningAdjudicatorAgent
)
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.blockchain.eth.registry import AllocationRegistry, EthereumContractRegistry
from nucypher.cli.deploy import deploy
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.utilities.sandbox.constants import (
    INSECURE_DEVELOPMENT_PASSWORD,
    TEST_PROVIDER_URI,
    MOCK_ALLOCATION_INFILE,
    MOCK_REGISTRY_FILEPATH, MOCK_ALLOCATION_REGISTRY_FILEPATH)


def test_nucypher_deploy_contracts(testerchain, click_runner, mock_primary_registry_filepath):

    # We start with a blockchain node, and nothing else...
    assert not os.path.isfile(mock_primary_registry_filepath)

    command = ('deploy',
               '--registry-outfile', mock_primary_registry_filepath,
               '--provider-uri', TEST_PROVIDER_URI,
               '--poa')

    user_input = 'Y\n'+f'{INSECURE_DEVELOPMENT_PASSWORD}\n'*8
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

                            # Additional Upgrades
                            'MinersEscrow',        # v3
                            'MinersEscrow',        # v4
                            'MiningAdjudicator',   # v3
                            'PolicyAgent,',        # v3
                            'UserEscrowProxy'      # v3
                            )

    executed_upgrades = {name: 0 for name in set(contracts_to_upgrade)}

    blockchain = Blockchain.connect(registry=EthereumContractRegistry(registry_filepath=MOCK_REGISTRY_FILEPATH))

    yes = 'Y\n'
    version_1_secret = f'{INSECURE_DEVELOPMENT_PASSWORD}\n' * 2
    version_2_secret = f'{INSECURE_DEVELOPMENT_PASSWORD[::-1]}\n' * 2
    version_3_secret = f'{INSECURE_DEVELOPMENT_PASSWORD[2:-2:-1]}\n' * 2
    version_4_secret = f'{INSECURE_DEVELOPMENT_PASSWORD[1:-3:-1]}\n' * 2

    user_input_1_to_2 = yes + version_1_secret + version_2_secret
    user_input_2_to_3 = yes + version_2_secret + version_3_secret
    user_input_3_to_4 = yes + version_3_secret + version_4_secret

    user_inputs = {0: user_input_1_to_2,
                   1: user_input_2_to_3,
                   2: user_input_3_to_4}

    expected_registrations = 9
    with open(MOCK_REGISTRY_FILEPATH, 'r') as file:
        raw_registry_data = file.read()
        registry_data = json.loads(raw_registry_data)
        assert len(registry_data) == expected_registrations

    for contract_name in contracts_to_upgrade:

        command = ('upgrade',
                   '--contract-name', contract_name,
                   '--registry-infile', MOCK_REGISTRY_FILEPATH,
                   '--provider-uri', TEST_PROVIDER_URI,
                   '--poa')

        user_input = user_inputs[executed_upgrades[contract_name]]
        result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
        assert result.exit_code == 0

        executed_upgrades[contract_name] += 1
        expected_registrations += 1

        with open(MOCK_REGISTRY_FILEPATH, 'r') as file:
            raw_registry_data = file.read()
            registry_data = json.loads(raw_registry_data)
            assert len(registry_data) == expected_registrations

            # Check that there is more than one entry, since we've deployed a "version 2"
            registered_names = [r[0] for r in registry_data]
            assert registered_names.count(contract_name) == 2

        # Ensure deployments are different addresses
        records = blockchain.interface.registry.search(contract_name=contract_name)
        assert len(records) == executed_upgrades[contract_name] + 1

        # Get the last two entries
        old, new = records[-2:]
        old_name, old_address, *abi = old
        new_name, new_address, *abi = new
        assert old_name == new_name
        assert old_address != new_address

        # Ensure the proxy targets the new deployment
        proxy_name = 'Dispatcher' if contract_name != "UserEscrowProxy" else "UserEscrowLibraryLinker"
        proxy = blockchain.interface.get_proxy(target_address=new_address, proxy_name=proxy_name)
        targeted_address = proxy.functions.target().call()
        assert targeted_address != old_address
        assert targeted_address == new_address


def test_rollback(click_runner):
    """Roll 'em all back!"""

    contracts_to_rollback = ('MinersEscrow', 'PolicyManager', 'MiningAdjudicator')

    user_input = 'Y\n' \
                 + f'{INSECURE_DEVELOPMENT_PASSWORD[::-1]}\n' * 2 \
                 + f'{INSECURE_DEVELOPMENT_PASSWORD}\n' * 2

    blockchain = Blockchain.connect(registry=EthereumContractRegistry(registry_filepath=MOCK_REGISTRY_FILEPATH))

    for contract_name in contracts_to_rollback:

        command = ('rollback',
                   '--contract-name', contract_name,
                   '--registry-infile', MOCK_REGISTRY_FILEPATH,
                   '--provider-uri', TEST_PROVIDER_URI,
                   '--poa')

        result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
        assert result.exit_code == 0

        records = blockchain.interface.registry.search(contract_name='UserEscrowProxy')
        assert len(records) == 2

        old, new = records
        _name, old_address, *abi = old
        _name, new_address, *abi = new
        assert old_address != new_address

        # Ensure the proxy targets the old deployment
        proxy_name = 'Dispatcher'
        proxy = blockchain.interface.get_proxy(target_address=new_address, proxy_name=proxy_name)
        targeted_address = proxy.functions.target().call()
        assert targeted_address != new_address
        assert targeted_address == old_address


def test_nucypher_deploy_allocations(testerchain, click_runner, mock_allocation_infile, token_economics):

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
    assert user_escrow_agent.unvested_tokens == token_economics.maximum_allowed_locked


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
    assert DEFAULT_CONFIG_ROOT not in result.output, 'WARNING: Deploy CLI tests are using default config root dir!'
    assert f'Successfully destroyed {mock_primary_registry_filepath}' in result.output
    assert not os.path.isfile(mock_primary_registry_filepath)
