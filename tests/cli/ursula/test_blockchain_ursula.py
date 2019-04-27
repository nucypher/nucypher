import json
import os
import random

import datetime
import maya
import pytest

from nucypher.blockchain.eth.actors import Miner
from nucypher.blockchain.eth.agents import NucypherTokenAgent, MinerAgent
from nucypher.blockchain.eth.token import NU
from nucypher.characters.lawful import Enrico
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.utilities.sandbox import constants
from nucypher.utilities.sandbox.blockchain import token_airdrop
from nucypher.utilities.sandbox.constants import (
    MOCK_IP_ADDRESS,
    TEST_PROVIDER_URI,
    MOCK_URSULA_STARTING_PORT,
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_REGISTRY_FILEPATH,
    TEMPORARY_DOMAIN,
    DEVELOPMENT_ETH_AIRDROP_AMOUNT)
from nucypher.utilities.sandbox.middleware import MockRestMiddleware
from nucypher.utilities.sandbox.ursula import start_pytest_ursula_services

from web3 import Web3


@pytest.fixture(scope='module')
def stake_value(token_economics):
    value = NU(token_economics.minimum_allowed_locked * 2, 'NuNit')
    return value


@pytest.fixture(scope='module')
def policy_rate():
    rate = Web3.toWei(21, 'gwei')
    return rate


@pytest.fixture(scope='module')
def policy_value(token_economics, policy_rate):
    value = policy_rate * token_economics.minimum_locked_periods  # * len(ursula)
    return value


@pytest.fixture(autouse=True, scope='module')
def funded_blockchain(deployed_blockchain, token_economics):

    # Who are ya'?
    blockchain, _deployer_address, registry = deployed_blockchain
    deployer_address, *everyone_else, staking_participant = blockchain.interface.w3.eth.accounts

    # Free ETH!!!
    blockchain.ether_airdrop(amount=DEVELOPMENT_ETH_AIRDROP_AMOUNT)

    # Free Tokens!!!
    token_airdrop(token_agent=NucypherTokenAgent(blockchain=blockchain),
                  origin=_deployer_address,
                  addresses=everyone_else,
                  amount=token_economics.minimum_allowed_locked*5)

    # HERE YOU GO
    yield blockchain, _deployer_address


@pytest.fixture(scope='module')
def staking_participant(funded_blockchain, blockchain_ursulas):
    # Start up the local fleet
    for teacher in blockchain_ursulas:
        start_pytest_ursula_services(ursula=teacher)

    teachers = list(blockchain_ursulas)
    staking_participant = teachers[-1]
    return staking_participant


@pytest.fixture(scope='module')
def configuration_file_location(custom_filepath):
    _configuration_file_location = os.path.join(constants.MOCK_CUSTOM_INSTALLATION_PATH, 'ursula.config')
    return _configuration_file_location


@pytest.fixture(scope='module')
def mock_registry_filepath(deployed_blockchain):

    _blockchain, _deployer_address, _registry = deployed_blockchain

    # Fake the source contract registry
    with open(MOCK_REGISTRY_FILEPATH, 'w') as file:
        file.write(json.dumps(_registry.read()))

    yield MOCK_REGISTRY_FILEPATH

    if os.path.isfile(MOCK_REGISTRY_FILEPATH):
        os.remove(MOCK_REGISTRY_FILEPATH)


def test_initialize_system_blockchain_configuration(click_runner,
                                                    custom_filepath,
                                                    mock_registry_filepath,
                                                    staking_participant):

    init_args = ('ursula', 'init',
                 '--poa',
                 '--network', str(TEMPORARY_DOMAIN, encoding='utf-8'),
                 '--checksum-address', staking_participant.checksum_public_address,
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
        assert config_data['checksum_public_address'] == staking_participant.checksum_public_address
        assert str(TEMPORARY_DOMAIN, encoding='utf-8') in config_data['domains']


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
    stakes = list(miner_agent.get_all_stakes(miner_address=config_data['checksum_public_address']))
    assert len(stakes) == 1
    start_period, end_period, value = stakes[0]
    assert NU(int(value), 'NuNit') == stake_value


def test_list_ursula_stakes(click_runner,
                            funded_blockchain,
                            configuration_file_location,
                            stake_value):

    _blockchain, _deployer_address = funded_blockchain

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
                               funded_blockchain,
                               alice_blockchain_test_config,
                               bob_blockchain_test_config,
                               random_policy_label,
                               blockchain_ursulas,
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
                                     alice_blockchain_test_config,
                                     bob_blockchain_test_config,
                                     random_policy_label,
                                     blockchain_ursulas,
                                     staking_participant,
                                     token_economics,
                                     policy_value,
                                     policy_rate):

    blockchain = staking_participant.blockchain

    half_stake_time = token_economics.minimum_locked_periods // 2          # Test setup
    logger = staking_participant.log  # Enter the Teacher's Logger, and
    current_period = 1                # State the initial period for incrementing

    miner = Miner(checksum_address=staking_participant.checksum_public_address,
                  blockchain=blockchain, is_me=True)

    pre_stake_eth_balance = miner.eth_balance

    # Finish the passage of time... once and for all
    for _ in range(half_stake_time):
        current_period += 1
        logger.debug(f"period {current_period}")
        blockchain.time_travel(periods=1)
        miner.confirm_activity()

    # Alice creates a policy and grants Bob access
    alice = alice_blockchain_test_config.produce()
    bob = bob_blockchain_test_config.produce()

    M, N = 1, 1
    expiration = maya.now() + datetime.timedelta(days=3)
    blockchain_policy = alice.grant(bob=bob,
                                    label=random_policy_label,
                                    m=M, n=N,
                                    value=policy_value,
                                    expiration=expiration,
                                    handpicked_ursulas={staking_participant})

    # Bob joins the policy
    bob.join_policy(random_policy_label, bytes(alice.stamp))

    # Enrico Encrypts (of course)
    enrico = Enrico(policy_encrypting_key=blockchain_policy.public_key,
                    network_middleware=MockRestMiddleware())

    verifying_key = alice.stamp.as_umbral_pubkey()

    for index in range(half_stake_time-5):
        logger.debug(f"period {current_period}")
        random_data = os.urandom(random.randrange(20, 100))
        ciphertext, signature = enrico.encrypt_message(message=random_data)

        # Retrieve
        cleartexts = bob.retrieve(message_kit=ciphertext,
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
