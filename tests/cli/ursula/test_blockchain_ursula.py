import json
import os
import random

import datetime
import maya
import pytest

from nucypher.blockchain.eth.actors import Miner
from nucypher.blockchain.eth.agents import MinerAgent
from nucypher.blockchain.eth.token import NU
from nucypher.characters.lawful import Enrico
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration, BobConfiguration
from nucypher.utilities.sandbox.constants import (
    MOCK_CUSTOM_INSTALLATION_PATH,
    MOCK_IP_ADDRESS,
    TEST_PROVIDER_URI,
    MOCK_URSULA_STARTING_PORT,
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_REGISTRY_FILEPATH,
    TEMPORARY_DOMAIN,
)
from nucypher.utilities.sandbox.middleware import MockRestMiddleware


@pytest.fixture(scope='module')
def configuration_file_location(custom_filepath):
    _configuration_file_location = os.path.join(MOCK_CUSTOM_INSTALLATION_PATH, 'ursula.config')
    return _configuration_file_location


@pytest.fixture(scope="module")
def charlie_blockchain_test_config(blockchain_ursulas, three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    etherbase, alice_address, bob_address, *everyone_else = token_agent.blockchain.interface.w3.eth.accounts

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
def mock_registry_filepath(testerchain):

    registry = testerchain.interface.registry

    # Fake the source contract registry
    with open(MOCK_REGISTRY_FILEPATH, 'w') as file:
        file.write(json.dumps(registry.read()))

    yield MOCK_REGISTRY_FILEPATH

    if os.path.isfile(MOCK_REGISTRY_FILEPATH):
        os.remove(MOCK_REGISTRY_FILEPATH)


def test_initialize_system_blockchain_configuration(click_runner,
                                                    custom_filepath,
                                                    mock_registry_filepath,
                                                    staking_participant):

    init_args = ('ursula', 'init',
                 '--poa',
                 '--network', TEMPORARY_DOMAIN,
                 '--checksum-address', staking_participant.checksum_address,
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

    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.CONFIG_FILENAME)
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    with open(custom_config_filepath, 'r') as config_file:
        raw_config_data = config_file.read()
        config_data = json.loads(raw_config_data)
        assert config_data['provider_uri'] == TEST_PROVIDER_URI
        assert config_data['checksum_address'] == staking_participant.checksum_address
        assert TEMPORARY_DOMAIN in config_data['domains']


def test_init_ursula_stake(click_runner,
                           configuration_file_location,
                           funded_blockchain,
                           stake_value,
                           token_economics):

    stake_args = ('ursula', 'stake',
                  '--config-file', configuration_file_location,
                  '--value', stake_value.to_tokens(),
                  '--duration', token_economics.minimum_locked_periods,
                  '--poa',
                  '--force')

    result = click_runner.invoke(nucypher_cli, stake_args, input=INSECURE_DEVELOPMENT_PASSWORD, catch_exceptions=False)
    assert result.exit_code == 0

    with open(configuration_file_location, 'r') as config_file:
        config_data = json.loads(config_file.read())

    # Verify the stake is on-chain
    miner_agent = MinerAgent()
    stakes = list(miner_agent.get_all_stakes(miner_address=config_data['checksum_address']))
    assert len(stakes) == 1
    start_period, end_period, value = stakes[0]
    assert NU(int(value), 'NuNit') == stake_value


def test_list_ursula_stakes(click_runner,
                            funded_blockchain,
                            configuration_file_location,
                            stake_value):
    stake_args = ('ursula', 'stake',
                  '--config-file', configuration_file_location,
                  '--list',
                  '--poa')

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}'
    result = click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert str(stake_value) in result.output


def test_ursula_divide_stakes(click_runner, configuration_file_location, token_economics):

    divide_args = ('ursula', 'stake',
                   '--divide',
                   '--config-file', configuration_file_location,
                   '--poa',
                   '--force',
                   '--index', 0,
                   '--value', NU(token_economics.minimum_allowed_locked, 'NuNit').to_tokens(),
                   '--duration', 10)

    result = click_runner.invoke(nucypher_cli,
                                 divide_args,
                                 catch_exceptions=False,
                                 env=dict(NUCYPHER_KEYRING_PASSWORD=INSECURE_DEVELOPMENT_PASSWORD))
    assert result.exit_code == 0

    stake_args = ('ursula', 'stake',
                  '--config-file', configuration_file_location,
                  '--list',
                  '--poa')

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}'
    result = click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert str(NU(token_economics.minimum_allowed_locked, 'NuNit').to_tokens()) in result.output


def test_run_blockchain_ursula(click_runner,
                               configuration_file_location,
                               staking_participant):
    # Now start running your Ursula!
    init_args = ('ursula', 'run',
                 '--poa',
                 '--dry-run',
                 '--config-file', configuration_file_location)

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}'
    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0


def test_collect_rewards_integration(click_runner,
                                     configuration_file_location,
                                     blockchain_alice,
                                     blockchain_bob,
                                     random_policy_label,
                                     blockchain_ursulas,
                                     staking_participant,
                                     token_economics,
                                     policy_value,
                                     policy_rate):

    blockchain = staking_participant.blockchain

    half_stake_time = token_economics.minimum_locked_periods // 2  # Test setup
    logger = staking_participant.log  # Enter the Teacher's Logger, and
    current_period = 1  # State the initial period for incrementing

    miner = Miner(checksum_address=staking_participant.checksum_address,
                  blockchain=blockchain, is_me=True)

    pre_stake_eth_balance = miner.eth_balance

    # Finish the passage of time... once and for all
    for _ in range(half_stake_time):
        current_period += 1
        logger.debug(f"period {current_period}")
        blockchain.time_travel(periods=1)
        miner.confirm_activity()

    # Alice creates a policy and grants Bob access
    M, N = 1, 1
    expiration = maya.now() + datetime.timedelta(days=3)
    blockchain_policy = blockchain_alice.grant(bob=blockchain_bob,
                                               label=random_policy_label,
                                               m=M, n=N,
                                               value=policy_value,
                                               expiration=expiration,
                                               handpicked_ursulas={staking_participant})

    # Bob learns about the new staker and joins the policy
    blockchain_bob.start_learning_loop()
    blockchain_bob.remember_node(node=staking_participant)
    blockchain_bob.join_policy(random_policy_label, bytes(blockchain_alice.stamp))

    # Enrico Encrypts (of course)
    enrico = Enrico(policy_encrypting_key=blockchain_policy.public_key,
                    network_middleware=MockRestMiddleware())

    verifying_key = blockchain_alice.stamp.as_umbral_pubkey()

    for index in range(half_stake_time - 5):
        logger.debug(f"period {current_period}")
        random_data = os.urandom(random.randrange(20, 100))
        ciphertext, signature = enrico.encrypt_message(message=random_data)

        # Retrieve
        cleartexts = blockchain_bob.retrieve(message_kit=ciphertext,
                                             data_source=enrico,
                                             alice_verifying_key=verifying_key,
                                             label=random_policy_label)
        assert random_data == cleartexts[0]

        # Ursula Staying online and the clock advancing
        blockchain.time_travel(periods=1)
        miner.confirm_activity()
        current_period += 1

    # Finish the passage of time... once and for all
    for _ in range(5):
        current_period += 1
        logger.debug(f"period {current_period}")
        blockchain.time_travel(periods=1)
        miner.confirm_activity()

    #
    # WHERES THE MONEY URSULA?? - Collecting Rewards
    #

    # The address the client wants Ursula to send rewards to
    burner_wallet = blockchain.interface.w3.eth.account.create(INSECURE_DEVELOPMENT_PASSWORD)
    # The rewards wallet is initially empty
    assert blockchain.interface.w3.eth.getBalance(burner_wallet.address) == 0

    # Snag a random teacher from the fleet
    random_teacher = list(blockchain_ursulas).pop()

    collection_args = ('--mock-networking',
                       'ursula', 'collect-reward',
                       '--rest-host', MOCK_IP_ADDRESS,
                       '--teacher-uri', random_teacher.rest_interface,
                       '--config-file', configuration_file_location,
                       '--withdraw-address', burner_wallet.address,
                       '--poa',
                       '--force')

    result = click_runner.invoke(nucypher_cli,
                                 collection_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    collected_reward = blockchain.interface.w3.eth.getBalance(burner_wallet.address)
    assert collected_reward != 0

    expected_reward = policy_rate * 30
    assert collected_reward == expected_reward
    assert miner.eth_balance == pre_stake_eth_balance
