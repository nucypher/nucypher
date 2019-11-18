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

import datetime
import json
import os
import random

import maya
from twisted.logger import Logger

from nucypher.blockchain.eth.actors import Staker
from nucypher.blockchain.eth.agents import StakingEscrowAgent, ContractAgency
from nucypher.blockchain.eth.token import NU, Stake
from nucypher.characters.lawful import Enrico, Ursula
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration, StakeHolderConfiguration
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import (
    MOCK_IP_ADDRESS,
    TEST_PROVIDER_URI,
    MOCK_URSULA_STARTING_PORT,
    INSECURE_DEVELOPMENT_PASSWORD,
    TEMPORARY_DOMAIN,
    MOCK_KNOWN_URSULAS_CACHE,
    select_test_port,
)
from nucypher.utilities.sandbox.middleware import MockRestMiddleware


def test_new_stakeholder(click_runner,
                         custom_filepath,
                         mock_registry_filepath,
                         testerchain):

    init_args = ('stake', 'init-stakeholder',
                 '--poa',
                 '--config-root', custom_filepath,
                 '--provider', TEST_PROVIDER_URI,
                 '--registry-filepath', mock_registry_filepath)

    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False)
    assert result.exit_code == 0

    # Files and Directories
    assert os.path.isdir(custom_filepath), 'Configuration file does not exist'

    custom_config_filepath = os.path.join(custom_filepath, StakeHolderConfiguration.generate_filename())
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    with open(custom_config_filepath, 'r') as config_file:
        raw_config_data = config_file.read()
        config_data = json.loads(raw_config_data)
        assert config_data['provider_uri'] == TEST_PROVIDER_URI


def test_stake_init(click_runner,
                    stakeholder_configuration_file_location,
                    stake_value,
                    mock_registry_filepath,
                    token_economics,
                    testerchain,
                    test_registry,
                    agency,
                    manual_staker):

    # Staker address has not stakes
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    stakes = list(staking_agent.get_all_stakes(staker_address=manual_staker))
    assert not stakes

    stake_args = ('stake', 'create',
                  '--config-file', stakeholder_configuration_file_location,
                  '--staking-address', manual_staker,
                  '--value', stake_value.to_tokens(),
                  '--lock-periods', token_economics.minimum_locked_periods,
                  '--force')

    # TODO: This test is writing to the default system directory and ignoring updates to the passed filepath
    user_input = f'0\n' + f'{INSECURE_DEVELOPMENT_PASSWORD}\n' + f'Y\n'
    result = click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # Test integration with BaseConfiguration
    with open(stakeholder_configuration_file_location, 'r') as config_file:
        _config_data = json.loads(config_file.read())

    # Verify the stake is on-chain
    # Test integration with Agency
    stakes = list(staking_agent.get_all_stakes(staker_address=manual_staker))
    assert len(stakes) == 1

    # Test integration with NU
    start_period, end_period, value = stakes[0]
    assert NU(int(value), 'NuNit') == stake_value
    assert (end_period - start_period) == token_economics.minimum_locked_periods - 1

    # Test integration with Stake
    stake = Stake.from_stake_info(index=0,
                                  checksum_address=manual_staker,
                                  stake_info=stakes[0],
                                  staking_agent=staking_agent,
                                  economics=token_economics)
    assert stake.value == stake_value
    assert stake.duration == token_economics.minimum_locked_periods


def test_stake_list(click_runner,
                    stakeholder_configuration_file_location,
                    stake_value,
                    mock_registry_filepath,
                    testerchain):

    stake_args = ('stake', 'list',
                  '--config-file', stakeholder_configuration_file_location)

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert str(stake_value) in result.output


def test_staker_divide_stakes(click_runner,
                              stakeholder_configuration_file_location,
                              token_economics,
                              manual_staker,
                              testerchain,
                              test_registry):

    divide_args = ('stake', 'divide',
                   '--config-file', stakeholder_configuration_file_location,
                   '--force',
                   '--staking-address', manual_staker,
                   '--index', 0,
                   '--value', NU(token_economics.minimum_allowed_locked, 'NuNit').to_tokens(),
                   '--lock-periods', 10)

    result = click_runner.invoke(nucypher_cli,
                                 divide_args,
                                 catch_exceptions=False,
                                 env=dict(NUCYPHER_KEYRING_PASSWORD=INSECURE_DEVELOPMENT_PASSWORD))
    assert result.exit_code == 0

    stake_args = ('stake', 'list',
                  '--config-file', stakeholder_configuration_file_location,
                  '--poa')

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert str(NU(token_economics.minimum_allowed_locked, 'NuNit').to_tokens()) in result.output


def test_stake_set_worker(click_runner,
                          testerchain,
                          test_registry,
                          manual_staker,
                          manual_worker,
                          stakeholder_configuration_file_location):

    init_args = ('stake', 'set-worker',
                 '--config-file', stakeholder_configuration_file_location,
                 '--staking-address', manual_staker,
                 '--worker-address', manual_worker,
                 '--force')

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    staker = Staker(is_me=True, checksum_address=manual_staker, registry=test_registry)

    assert staker.worker_address == manual_worker


def test_ursula_init(click_runner,
                     custom_filepath,
                     mock_registry_filepath,
                     manual_staker,
                     manual_worker,
                     testerchain):

    init_args = ('ursula', 'init',
                 '--poa',
                 '--network', TEMPORARY_DOMAIN,
                 '--staker-address', manual_staker,
                 '--worker-address', manual_worker,
                 '--config-root', custom_filepath,
                 '--provider', TEST_PROVIDER_URI,
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
        assert config_data['worker_address'] == manual_worker
        assert config_data['checksum_address'] == manual_staker
        assert TEMPORARY_DOMAIN in config_data['domains']


def test_ursula_run(click_runner,
                    manual_worker,
                    manual_staker,
                    custom_filepath,
                    testerchain):

    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.generate_filename())

    # Now start running your Ursula!
    init_args = ('ursula', 'run',
                 '--dry-run',
                 '--config-file', custom_config_filepath)

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}\n' * 2
    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0


def test_stake_restake(click_runner,
                       manual_staker,
                       custom_filepath,
                       testerchain,
                       test_registry,
                       stakeholder_configuration_file_location):

    staker = Staker(is_me=True, checksum_address=manual_staker, registry=test_registry)
    assert staker.is_restaking

    restake_args = ('stake', 'restake',
                    '--disable',
                    '--config-file', stakeholder_configuration_file_location,
                    '--staking-address', manual_staker,
                    '--force')

    result = click_runner.invoke(nucypher_cli,
                                 restake_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert not staker.is_restaking
    assert "Successfully disabled" in result.output

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    current_period = staking_agent.get_current_period()
    release_period = current_period + 1
    lock_args = ('stake', 'restake',
                 '--lock-until', release_period,
                 '--config-file', stakeholder_configuration_file_location,
                 '--staking-address', manual_staker,
                 '--force')

    result = click_runner.invoke(nucypher_cli,
                                 lock_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    # Still not staking and the lock is enabled
    assert not staker.is_restaking
    assert staker.restaking_lock_enabled

    # CLI Output includes success message
    assert "Successfully enabled" in result.output
    assert str(release_period) in result.output

    # Wait until release period
    testerchain.time_travel(periods=1)
    assert not staker.restaking_lock_enabled
    assert not staker.is_restaking

    disable_args = ('stake', 'restake',
                    '--enable',
                    '--config-file', stakeholder_configuration_file_location,
                    '--staking-address', manual_staker,
                    '--force')

    result = click_runner.invoke(nucypher_cli,
                                 disable_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert staker.is_restaking
    assert "Successfully enabled" in result.output


def test_collect_rewards_integration(click_runner,
                                     testerchain,
                                     test_registry,
                                     stakeholder_configuration_file_location,
                                     blockchain_alice,
                                     blockchain_bob,
                                     random_policy_label,
                                     manual_staker,
                                     manual_worker,
                                     token_economics,
                                     mock_transacting_power_activation,
                                     policy_value,
                                     policy_rate):

    half_stake_time = token_economics.minimum_locked_periods // 2  # Test setup
    logger = Logger("Test-CLI")  # Enter the Teacher's Logger, and
    current_period = 0  # State the initial period for incrementing

    staker_address = manual_staker
    worker_address = manual_worker

    staker = Staker(is_me=True, checksum_address=staker_address, registry=test_registry)
    staker.stakes.refresh()

    # The staker is staking.
    assert staker.is_staking
    assert staker.stakes
    assert staker.worker_address == worker_address

    ursula_port = select_test_port()
    ursula = Ursula(is_me=True,
                    checksum_address=staker_address,
                    worker_address=worker_address,
                    registry=test_registry,
                    rest_host='127.0.0.1',
                    rest_port=ursula_port,
                    network_middleware=MockRestMiddleware())

    MOCK_KNOWN_URSULAS_CACHE[ursula_port] = ursula
    assert ursula.worker_address == worker_address
    assert ursula.checksum_address == staker_address

    mock_transacting_power_activation(account=worker_address, password=INSECURE_DEVELOPMENT_PASSWORD)

    # Confirm for half the first stake duration
    for _ in range(half_stake_time):
        logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")
        ursula.confirm_activity()
        testerchain.time_travel(periods=1)
        current_period += 1

    # Alice creates a policy and grants Bob access
    blockchain_alice.selection_buffer = 1

    M, N = 1, 1
    days = 3
    now = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    expiration = maya.MayaDT(now).add(days=days-1)
    blockchain_policy = blockchain_alice.grant(bob=blockchain_bob,
                                               label=random_policy_label,
                                               m=M, n=N,
                                               value=policy_value,
                                               expiration=expiration,
                                               handpicked_ursulas={ursula})

    # Ensure that the handpicked Ursula was selected for the policy
    arrangement = list(blockchain_policy._accepted_arrangements)[0]
    assert arrangement.ursula == ursula

    # Bob learns about the new staker and joins the policy
    blockchain_bob.start_learning_loop()
    blockchain_bob.remember_node(node=ursula)
    blockchain_bob.join_policy(random_policy_label, bytes(blockchain_alice.stamp))

    # Enrico Encrypts (of course)
    enrico = Enrico(policy_encrypting_key=blockchain_policy.public_key,
                    network_middleware=MockRestMiddleware())

    verifying_key = blockchain_alice.stamp.as_umbral_pubkey()

    for index in range(half_stake_time - 5):
        logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")
        ursula.confirm_activity()

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
        current_period += 1

    # Finish the passage of time for the first Stake
    for _ in range(5):  # plus the extended periods from stake division
        logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")
        ursula.confirm_activity()
        testerchain.time_travel(periods=1)
        current_period += 1

    #
    # WHERES THE MONEY URSULA?? - Collecting Rewards
    #

    # The address the client wants Ursula to send rewards to
    burner_wallet = testerchain.w3.eth.account.create(INSECURE_DEVELOPMENT_PASSWORD)

    # The rewards wallet is initially empty, because it is freshly created
    assert testerchain.client.get_balance(burner_wallet.address) == 0

    # Rewards will be unlocked after the
    # final confirmed period has passed (+1).
    logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")
    testerchain.time_travel(periods=1)
    current_period += 1
    logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")

    # At least half of the tokens are unlocked (restaking was enabled for some prior periods)
    assert staker.locked_tokens() >= token_economics.minimum_allowed_locked

    # Since we are mocking the blockchain connection, manually consume the transacting power of the Staker.
    mock_transacting_power_activation(account=staker_address, password=INSECURE_DEVELOPMENT_PASSWORD)

    # Collect Policy Reward
    collection_args = ('stake', 'collect-reward',
                       '--mock-networking',
                       '--config-file', stakeholder_configuration_file_location,
                       '--policy-reward',
                       '--no-staking-reward',
                       '--staking-address', staker_address,
                       '--withdraw-address', burner_wallet.address)
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
        ursula.confirm_activity()
        current_period += 1
        logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")
        testerchain.time_travel(periods=1)

    #
    # Collect Staking Reward
    #

    balance_before_collecting = staker.token_agent.get_balance(address=staker_address)

    collection_args = ('stake', 'collect-reward',
                       '--mock-networking',
                       '--config-file', stakeholder_configuration_file_location,
                       '--no-policy-reward',
                       '--staking-reward',
                       '--staking-address', staker_address,
                       '--force')

    result = click_runner.invoke(nucypher_cli,
                                 collection_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    # The staker has withdrawn her staking rewards
    assert staker.token_agent.get_balance(address=staker_address) >= balance_before_collecting


def test_stake_detach_worker(click_runner,
                             testerchain,
                             manual_staker,
                             manual_worker,
                             test_registry,
                             stakeholder_configuration_file_location):

    staker = Staker(is_me=True,
                    checksum_address=manual_staker,
                    registry=test_registry)

    assert staker.worker_address == manual_worker

    init_args = ('stake', 'detach-worker',
                 '--config-file', stakeholder_configuration_file_location,
                 '--staking-address', manual_staker,
                 )

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}'
    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    staker = Staker(is_me=True,
                    checksum_address=manual_staker,
                    registry=test_registry)

    assert not staker.worker_address
