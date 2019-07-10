import json
import os
import random

import datetime
import maya
import pytest

from nucypher.blockchain.eth.actors import Staker, StakeHolder, Worker
from nucypher.blockchain.eth.agents import StakingEscrowAgent, Agency
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterface
from nucypher.blockchain.eth.token import NU
from nucypher.characters.lawful import Enrico
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration, BobConfiguration
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import (
    MOCK_CUSTOM_INSTALLATION_PATH,
    MOCK_IP_ADDRESS,
    TEST_PROVIDER_URI,
    MOCK_URSULA_STARTING_PORT,
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_REGISTRY_FILEPATH,
    TEMPORARY_DOMAIN,
    NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS)
from nucypher.utilities.sandbox.middleware import MockRestMiddleware


@pytest.fixture(scope='module')
def worker_configuration_file_location(custom_filepath):
    _configuration_file_location = os.path.join(MOCK_CUSTOM_INSTALLATION_PATH, UrsulaConfiguration.generate_filename())
    return _configuration_file_location


@pytest.fixture(scope='module')
def staker_configuration_file_location(custom_filepath):
    _configuration_file_location = os.path.join(MOCK_CUSTOM_INSTALLATION_PATH, StakeHolder.generate_filename())
    return _configuration_file_location


@pytest.fixture(scope="module")
def charlie_blockchain_test_config(blockchain_ursulas, agency):
    token_agent, staking_agent, policy_agent = agency
    etherbase, alice_address, bob_address, *everyone_else = token_agent.blockchain.client.accounts

    config = BobConfiguration(dev_mode=True,
                              provider_uri=TEST_PROVIDER_URI,
                              checksum_address=bob_address,
                              network_middleware=MockRestMiddleware(),
                              known_nodes=blockchain_ursulas,
                              start_learning_now=False,
                              abort_on_learning_error=True,
                              federated_only=False,
                              download_registry=False,
                              save_metadata=False,
                              reload_metadata=False)
    yield config
    config.cleanup()


@pytest.fixture(scope='module')
def mock_registry_filepath(testerchain, agency):

    registry = testerchain.registry

    # Fake the source contract registry
    with open(MOCK_REGISTRY_FILEPATH, 'w') as file:
        file.write(json.dumps(registry.read()))

    yield MOCK_REGISTRY_FILEPATH

    if os.path.isfile(MOCK_REGISTRY_FILEPATH):
        os.remove(MOCK_REGISTRY_FILEPATH)


def test_new_stakeholder(click_runner,
                         custom_filepath,
                         mock_registry_filepath,
                         staking_participant,
                         testerchain):

    init_args = ('stake', 'new-stakeholder',
                 '--poa',
                 '--funding-address', testerchain.etherbase_account,
                 '--config-root', custom_filepath,
                 '--provider-uri', TEST_PROVIDER_URI,
                 '--registry-filepath', mock_registry_filepath)

    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    # Files and Directories
    assert os.path.isdir(custom_filepath), 'Configuration file does not exist'

    custom_config_filepath = os.path.join(custom_filepath, StakeHolder.generate_filename())
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    with open(custom_config_filepath, 'r') as config_file:
        raw_config_data = config_file.read()
        config_data = json.loads(raw_config_data)
        assert len(config_data['stakers']) == NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS
        assert config_data['blockchain']['provider_uri'] == TEST_PROVIDER_URI


def test_ursula_init(click_runner,
                     custom_filepath,
                     mock_registry_filepath,
                     staking_participant,
                     testerchain):

    init_args = ('ursula', 'init',
                 '--poa',
                 '--network', TEMPORARY_DOMAIN,
                 '--staker-address', testerchain.etherbase_account,  # TODO: This is confusing.
                 '--worker-address', staking_participant.checksum_address,
                 '--config-root', custom_filepath,
                 '--provider-uri', TEST_PROVIDER_URI,
                 '--registry-filepath', mock_registry_filepath,
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--rest-port', MOCK_URSULA_STARTING_PORT)

    user_input = '{password}\n{password}'.format(password=INSECURE_DEVELOPMENT_PASSWORD)
    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    # Files and Directories
    assert os.path.isdir(custom_filepath), 'Configuration file does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'keyring')), 'Keyring does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'known_nodes')), 'known_nodes directory does not exist'

    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.generate_filename())
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    with open(custom_config_filepath, 'r') as config_file:
        raw_config_data = config_file.read()
        config_data = json.loads(raw_config_data)
        assert config_data['provider_uri'] == TEST_PROVIDER_URI
        assert config_data['checksum_address'] == staking_participant.checksum_address
        assert TEMPORARY_DOMAIN in config_data['domains']


def test_stake_init(click_runner,
                    staker_configuration_file_location,
                    funded_blockchain,
                    stake_value,
                    mock_registry_filepath,
                    token_economics,
                    testerchain,
                    agency):

    # Simulate "Reconnection"
    cached_blockchain = BlockchainInterface.reconnect()
    registry = cached_blockchain.registry
    assert registry.filepath == mock_registry_filepath

    def from_dict(*args, **kwargs):
        return testerchain
    BlockchainInterface.from_dict = from_dict

    stake_args = ('stake', 'init',
                  '--config-file', staker_configuration_file_location,
                  '--registry-filepath', mock_registry_filepath,
                  '--value', stake_value.to_nunits(),
                  '--duration', token_economics.minimum_locked_periods,
                  '--force')

    user_input = f'0\n' + f'{INSECURE_DEVELOPMENT_PASSWORD}\n' + f'Y\n'
    result = click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    with open(staker_configuration_file_location, 'r') as config_file:
        config_data = json.loads(config_file.read())

    # Verify the stake is on-chain
    staking_agent = Agency.get_agent(StakingEscrowAgent)
    stakes = list(staking_agent.get_all_stakes(staker_address=testerchain.etherbase_account))
    assert len(stakes) == 1
    start_period, end_period, value = stakes[0]
    assert NU(int(value), 'NuNit') == stake_value


def test_stake_list(click_runner,
                    funded_blockchain,
                    staker_configuration_file_location,
                    stake_value,
                    mock_registry_filepath,
                    testerchain):

    # Simulate "Reconnection"
    cached_blockchain = BlockchainInterface.reconnect()
    registry = cached_blockchain.registry
    assert registry.filepath == mock_registry_filepath

    def from_dict(*args, **kwargs):
        return testerchain
    BlockchainInterface.from_dict = from_dict

    stake_args = ('stake', 'list', '--config-file', staker_configuration_file_location)

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}'
    result = click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert str(stake_value) in result.output


def test_ursula_divide_stakes(click_runner,
                              staker_configuration_file_location,
                              token_economics,
                              testerchain):

    divide_args = ('stake', 'divide',
                   '--config-file', staker_configuration_file_location,
                   '--force',
                   '--staking-address', testerchain.etherbase_account,
                   '--index', 0,
                   '--value', NU(token_economics.minimum_allowed_locked, 'NuNit').to_tokens(),
                   '--duration', 10)

    result = click_runner.invoke(nucypher_cli,
                                 divide_args,
                                 catch_exceptions=False,
                                 env=dict(NUCYPHER_KEYRING_PASSWORD=INSECURE_DEVELOPMENT_PASSWORD))
    assert result.exit_code == 0

    stake_args = ('stake', 'list',
                  '--config-file', staker_configuration_file_location,
                  '--poa')

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}'
    result = click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert str(NU(token_economics.minimum_allowed_locked, 'NuNit').to_tokens()) in result.output


def test_stake_set_worker(click_runner,
                          testerchain,
                          staker_configuration_file_location,
                          staking_participant):

    init_args = ('stake', 'set-worker',
                 '--config-file', staker_configuration_file_location,
                 '--staking-address', testerchain.etherbase_account,
                 '--worker-address', testerchain.etherbase_account,
                 '--force')

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}'
    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0


def test_run_blockchain_ursula(click_runner,
                               worker_configuration_file_location,
                               staking_participant):
    # Now start running your Ursula!
    init_args = ('ursula', 'run',
                 '--dry-run',
                 '--config-file', worker_configuration_file_location)

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}'
    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0


def test_collect_rewards_integration(click_runner,
                                     testerchain,
                                     staker_configuration_file_location,
                                     blockchain_alice,
                                     blockchain_bob,
                                     random_policy_label,
                                     staking_participant,
                                     token_economics,
                                     policy_value,
                                     policy_rate):

    half_stake_time = token_economics.minimum_locked_periods // 2  # Test setup
    logger = staking_participant.log  # Enter the Teacher's Logger, and
    current_period = 1  # State the initial period for incrementing

    staker_address = staking_participant.checksum_address
    worker_address = staking_participant.worker_address

    staker = Staker(is_me=True,
                    checksum_address=staker_address,
                    blockchain=testerchain)

    # The staker is staking.
    assert staker.stakes
    assert staker.is_staking
    pre_stake_token_balance = staker.token_balance

    assert staker.worker_address == worker_address

    worker = Worker(is_me=True,
                    worker_address=worker_address,
                    checksum_address=staker_address,
                    blockchain=testerchain)

    # Mock TransactingPower consumption (Worker-Ursula)
    worker.blockchain.transacting_power = TransactingPower(account=worker_address, blockchain=testerchain)
    worker.blockchain.transacting_power.activate()

    # Confirm for half the first stake duration
    for _ in range(half_stake_time):
        current_period += 1
        logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")
        testerchain.time_travel(periods=1)
        worker.confirm_activity()

    # Alice creates a policy and grants Bob access
    blockchain_alice.selection_buffer = 1

    M, N = 1, 1
    expiration = maya.now() + datetime.timedelta(days=3)
    blockchain_policy = blockchain_alice.grant(bob=blockchain_bob,
                                               label=random_policy_label,
                                               m=M, n=N,
                                               value=policy_value,
                                               expiration=expiration,
                                               handpicked_ursulas={staking_participant})

    # Ensure that the handpicked Ursula was selected for the policy
    arrangement = list(blockchain_policy._accepted_arrangements)[0]
    assert arrangement.ursula == staking_participant

    # Bob learns about the new staker and joins the policy
    blockchain_bob.start_learning_loop()
    blockchain_bob.remember_node(node=staking_participant)
    blockchain_bob.join_policy(random_policy_label, bytes(blockchain_alice.stamp))

    # Enrico Encrypts (of course)
    enrico = Enrico(policy_encrypting_key=blockchain_policy.public_key,
                    network_middleware=MockRestMiddleware())

    verifying_key = blockchain_alice.stamp.as_umbral_pubkey()

    for index in range(half_stake_time - 5):
        logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")

        # Encrypt
        random_data = os.urandom(random.randrange(20, 100))
        ciphertext, signature = enrico.encrypt_message(message=random_data)

        # Decrypt
        cleartexts = blockchain_bob.retrieve(message_kit=ciphertext,
                                             data_source=enrico,
                                             alice_verifying_key=verifying_key,
                                             label=random_policy_label)
        assert random_data == cleartexts[0]

        # Ursula Staying online and the clock advancing
        testerchain.time_travel(periods=1)
        worker.confirm_activity()
        current_period += 1

    # Finish the passage of time for the first Stake
    for _ in range(5):  # plus the extended periods from stake division
        current_period += 1
        logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")
        testerchain.time_travel(periods=1)
        worker.confirm_activity()

    #
    # WHERES THE MONEY URSULA?? - Collecting Rewards
    #

    # The address the client wants Ursula to send rewards to
    burner_wallet = testerchain.w3.eth.account.create(INSECURE_DEVELOPMENT_PASSWORD)

    # The rewards wallet is initially empty, because it is freshly created
    assert testerchain.client.get_balance(burner_wallet.address) == 0

    # Snag a random teacher from the fleet
    collection_args = ('--mock-networking',
                       'stake', 'collect-reward',
                       '--config-file', staker_configuration_file_location,
                       '--staking-address', staker_address,
                       '--withdraw-address', burner_wallet.address,
                       '--force')

    result = click_runner.invoke(nucypher_cli,
                                 collection_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    # Policy Reward
    collected_policy_reward = testerchain.client.get_balance(burner_wallet.address)
    expected_collection = policy_rate * 30
    assert collected_policy_reward == expected_collection

    # Finish the passage of time... once and for all
    # Extended periods from stake division
    for _ in range(9):
        current_period += 1
        logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")
        testerchain.time_travel(periods=1)
        worker.confirm_activity()

    # Staking Reward
    calculated_reward = staker.staking_agent.calculate_staking_reward(checksum_address=staker.worker_address)
    assert calculated_reward
    assert staker.token_balance > pre_stake_token_balance
