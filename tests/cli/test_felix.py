import os

import pytest_twisted
from twisted.internet import threads
from twisted.internet.task import Clock

from nucypher.blockchain.eth.actors import Staker
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import BaseContractRegistry, LocalContractRegistry
from nucypher.blockchain.eth.token import NU
from nucypher.characters.chaotic import Felix
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import FelixConfiguration
from nucypher.utilities.sandbox.constants import (
    TEMPORARY_DOMAIN,
    TEST_PROVIDER_URI,
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_CUSTOM_INSTALLATION_PATH_2
)


@pytest_twisted.inlineCallbacks
def test_run_felix(click_runner,
                   testerchain,
                   test_registry,
                   agency,
                   deploy_user_input,
                   mock_primary_registry_filepath):

    clock = Clock()
    Felix._CLOCK = clock
    Felix.DISTRIBUTION_INTERVAL = 5     # seconds
    Felix.DISBURSEMENT_INTERVAL = 0.01  # hours
    Felix.STAGING_DELAY = 2  # seconds

    # Main thread (Flask)
    os.environ['NUCYPHER_FELIX_DB_SECRET'] = INSECURE_DEVELOPMENT_PASSWORD

    # Mock live contract registry reads
    LocalContractRegistry.read = lambda *a, **kw: test_registry.read()

    # Test subproc (Click)
    envvars = {'NUCYPHER_KEYRING_PASSWORD': INSECURE_DEVELOPMENT_PASSWORD,
               'NUCYPHER_FELIX_DB_SECRET': INSECURE_DEVELOPMENT_PASSWORD,
               'FLASK_DEBUG': '1'}

    # Felix creates a system configuration
    init_args = ('felix', 'init',
                 '--debug',
                 '--registry-filepath', mock_primary_registry_filepath,
                 '--checksum-address', testerchain.client.accounts[0],
                 '--config-root', MOCK_CUSTOM_INSTALLATION_PATH_2,
                 '--network', TEMPORARY_DOMAIN,
                 '--provider', TEST_PROVIDER_URI)

    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    configuration_file_location = os.path.join(MOCK_CUSTOM_INSTALLATION_PATH_2, FelixConfiguration.generate_filename())

    # Felix Creates a Database
    db_args = ('felix', 'createdb',
               '--debug',
               '--config-file', configuration_file_location,
               '--provider', TEST_PROVIDER_URI)

    result = click_runner.invoke(nucypher_cli, db_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    # Felix Runs Web Services
    def run_felix():
        args = ('felix', 'run',
                '--debug',
                '--config-file', configuration_file_location,
                '--provider', TEST_PROVIDER_URI,
                '--dry-run')

        run_result = click_runner.invoke(nucypher_cli, args, catch_exceptions=False, env=envvars)
        assert run_result.exit_code == 0
        return run_result

    # A (mocked) client requests Felix's services
    def request_felix_landing_page(_result):

        # Init an equal Felix to the already running one.
        felix_config = FelixConfiguration.from_configuration_file(filepath=configuration_file_location,
                                                                  registry_filepath=mock_primary_registry_filepath)

        felix_config.attach_keyring()
        felix_config.keyring.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
        felix = felix_config.produce()

        # Make a flask app
        web_app = felix.make_web_app()
        test_client = web_app.test_client()

        # Load the landing page
        response = test_client.get('/')
        assert response.status_code == 200

        # Register a new recipient
        response = test_client.post('/register', data={'staker_address': testerchain.client.accounts[-1]})
        assert response.status_code == 200

        return

    def time_travel(_result):
        clock.advance(amount=60)

    # Record starting ether balance
    recipient = testerchain.client.accounts[-1]
    staker = Staker(checksum_address=recipient,
                    registry=test_registry,
                    is_me=True)
    original_eth_balance = staker.eth_balance

    # Run the callbacks
    d = threads.deferToThread(run_felix)
    d.addCallback(request_felix_landing_page)
    d.addCallback(time_travel)

    yield d

    def confirm_airdrop(_results):
        recipient = testerchain.client.accounts[-1]
        staker = Staker(checksum_address=recipient,
                        registry=test_registry,
                        is_me=True)

        assert staker.token_balance == NU(15000, 'NU')

        # TODO: Airdrop Testnet Ethers?
        # new_eth_balance = original_eth_balance + testerchain.w3.fromWei(Felix.ETHER_AIRDROP_AMOUNT, 'ether')
        assert staker.eth_balance == original_eth_balance

    staged_airdrops = Felix._AIRDROP_QUEUE
    next_airdrop = staged_airdrops[0]
    next_airdrop.addCallback(confirm_airdrop)
    yield next_airdrop
