import time
from unittest import mock

import pytest
import pytest_twisted as pt
from twisted.internet import threads

from nucypher.blockchain.eth.actors import Operator
from nucypher.blockchain.eth.trackers.dkg import ActiveRitualTracker
from nucypher.characters.base import Learner
from nucypher.cli.literature import NO_CONFIGURATIONS_ON_DISK
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import (
    NUCYPHER_ENVVAR_KEYSTORE_PASSWORD,
    TEMPORARY_DOMAIN,
)
from nucypher.utilities.networking import LOOPBACK_ADDRESS
from tests.constants import (
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_IP_ADDRESS,
    TEST_ETH_PROVIDER_URI,
    TEST_POLYGON_PROVIDER_URI,
)
from tests.utils.ursula import select_test_port, start_pytest_ursula_services


@mock.patch('glob.glob', return_value=list())
def test_missing_configuration_file(_default_filepath_mock, click_runner):
    cmd_args = ('ursula', 'run', '--network', TEMPORARY_DOMAIN)
    result = click_runner.invoke(nucypher_cli, cmd_args, catch_exceptions=False)
    assert result.exit_code != 0
    configuration_type = UrsulaConfiguration.NAME
    assert NO_CONFIGURATIONS_ON_DISK.format(name=configuration_type.capitalize(),
                                            command=configuration_type) in result.output


@pt.inlineCallbacks
def test_ursula_run_with_prometheus_but_no_metrics_port(click_runner):
    args = (
        "ursula",
        "run",  # Stat Ursula Command
        "--debug",  # Display log output; Do not attach console
        "--dev",  # Run in development mode (local ephemeral node)
        "--dry-run",  # Disable twisted reactor in subprocess
        "--lonely",  # Do not load seednodes
        "--prometheus",  # Specify collection of prometheus metrics
        "--eth-endpoint",
        TEST_ETH_PROVIDER_URI,
        "--polygon-endpoint",
        TEST_POLYGON_PROVIDER_URI,
    )

    result = yield threads.deferToThread(
        click_runner.invoke, nucypher_cli, args, catch_exceptions=False
    )

    assert result.exit_code != 0
    expected_error = "Error: --metrics-port is required when using --prometheus"
    assert expected_error in result.output


@pt.inlineCallbacks
def test_run_lone_default_development_ursula(click_runner, ursulas, testerchain):
    deploy_port = select_test_port()
    args = (
        "ursula",
        "run",  # Stat Ursula Command
        "--debug",  # Display log output; Do not attach console
        "--rest-port",
        deploy_port,  # Network Port
        "--dev",  # Run in development mode (ephemeral node)
        "--dry-run",  # Disable twisted reactor in subprocess
        "--lonely",  # Do not load seednodes,
        "--operator-address",
        ursulas[0].operator_address,
        "--eth-endpoint",
        TEST_ETH_PROVIDER_URI,
        "--polygon-endpoint",
        TEST_ETH_PROVIDER_URI,
        "--pre-payment-network",
        TEMPORARY_DOMAIN,
    )

    result = yield threads.deferToThread(
        click_runner.invoke,
        nucypher_cli,
        args,
        catch_exceptions=False,
        input=INSECURE_DEVELOPMENT_PASSWORD + "\n",
    )

    time.sleep(Learner._SHORT_LEARNING_DELAY)
    assert result.exit_code == 0, result.output
    assert "Running" in result.output
    assert f"{LOOPBACK_ADDRESS}:{deploy_port}" in result.output

    reserved_ports = (UrsulaConfiguration.DEFAULT_REST_PORT, UrsulaConfiguration.DEFAULT_DEVELOPMENT_REST_PORT)
    assert deploy_port not in reserved_ports


@pt.inlineCallbacks
@pytest.mark.skip(
    reason="This test is failing, possibly related to poor support for --dev?"
)
def test_ursula_learns_via_cli(click_runner, ursulas, testerchain):
    # ERROR: requests.exceptions.ReadTimeout:
    # HTTPSConnectionPool(host='127.0.0.1', port=43043): Read timed out. (read timeout=2)

    # Establish a running Teacher Ursula

    teacher = list(ursulas)[0]
    teacher_uri = teacher.seed_node_metadata(as_teacher_uri=True)

    deploy_port = select_test_port()

    def run_ursula():
        start_pytest_ursula_services(ursula=teacher)
        args = (
            "ursula",
            "run",
            "--debug",  # Display log output; Do not attach console
            "--rest-port",
            deploy_port,  # Network Port
            "--teacher",
            teacher_uri,
            "--dev",  # Run in development mode (ephemeral node)
            "--dry-run",  # Disable twisted reactor
            "--operator-address",
            ursulas[0].operator_address,
            "--eth-endpoint",
            TEST_ETH_PROVIDER_URI,
            "--polygon-endpoint",
            TEST_ETH_PROVIDER_URI,
            "--pre-payment-network",
            TEMPORARY_DOMAIN,
        )

        return threads.deferToThread(
            click_runner.invoke,
            nucypher_cli,
            args,
            catch_exceptions=False,
            input=INSECURE_DEVELOPMENT_PASSWORD + "\n",
        )

    # Run the Callbacks
    d = run_ursula()
    yield d

    result = d.result

    assert result.exit_code == 0
    assert "Starting services" in result.output
    assert f"{LOOPBACK_ADDRESS}:{deploy_port}" in result.output

    reserved_ports = (UrsulaConfiguration.DEFAULT_REST_PORT, UrsulaConfiguration.DEFAULT_DEVELOPMENT_REST_PORT)
    assert deploy_port not in reserved_ports

    # Check that CLI Ursula reports that it remembers the teacher and saves the TLS certificate
    assert f"Saved TLS certificate for {LOOPBACK_ADDRESS}" in result.output


@pytest.mark.skip(reason="This test is poorly written and is failing.")
@pt.inlineCallbacks
def test_persistent_node_storage_integration(
    click_runner, custom_filepath, testerchain, ursulas, agency_local_registry, mocker
):
    mocker.patch.object(ActiveRitualTracker, "start")
    (
        alice,
        ursula,
        another_ursula,
        staking_provider,
        *all_yall,
    ) = testerchain.unassigned_accounts
    filename = UrsulaConfiguration.generate_filename()
    another_ursula_configuration_file_location = custom_filepath / filename

    init_args = (
        "ursula",
        "init",
        "--eth-endpoint",
        TEST_ETH_PROVIDER_URI,
        "--polygon-endpoint",
        TEST_POLYGON_PROVIDER_URI,
        "--operator-address",
        another_ursula,
        "--network",
        TEMPORARY_DOMAIN,
        "--pre-payment-network",
        TEMPORARY_DOMAIN,
        "--rest-host",
        MOCK_IP_ADDRESS,
        "--config-root",
        str(custom_filepath.absolute()),
        "--registry-filepath",
        str(agency_local_registry.filepath.absolute()),
    )

    envvars = {NUCYPHER_ENVVAR_KEYSTORE_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}
    result = click_runner.invoke(
        nucypher_cli, init_args, catch_exceptions=False, env=envvars
    )
    assert result.exit_code == 0

    teacher = ursulas[-1]
    teacher_uri = teacher.rest_information()[0].uri

    start_pytest_ursula_services(ursula=teacher)

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}\n'

    run_args = ('ursula', 'run',
                '--dry-run',
                '--debug',
                '--config-file', str(another_ursula_configuration_file_location.absolute()),
                '--teacher', teacher_uri)

    Operator.READY_TIMEOUT = 1
    with pytest.raises(Operator.ActorError):
        # Operator init success, but not bonded.
        result = yield threads.deferToThread(click_runner.invoke,
                                             nucypher_cli, run_args,
                                             catch_exceptions=False,
                                             input=user_input,
                                             env=envvars)
    assert result.exit_code == 0

    # Run an Ursula amidst the other configuration files
    run_args = ('ursula', 'run',
                '--dry-run',
                '--debug',
                '--config-file',  str(another_ursula_configuration_file_location.absolute()))

    with pytest.raises(Operator.ActorError):
        # Operator init success, but not bonded.
        result = yield threads.deferToThread(click_runner.invoke,
                                             nucypher_cli, run_args,
                                             catch_exceptions=False,
                                             input=user_input,
                                             env=envvars)
    assert result.exit_code == 0
