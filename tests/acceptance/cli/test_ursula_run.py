import time
from unittest import mock

import pytest
import pytest_twisted as pt
from eth_account import Account
from twisted.internet import threads

from nucypher.blockchain.eth.agents import (
    CoordinatorAgent,
    TACoApplicationAgent,
    TACoChildApplicationAgent,
)
from nucypher.characters.base import Learner
from nucypher.cli.literature import NO_CONFIGURATIONS_ON_DISK
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import (
    TEMPORARY_DOMAIN_NAME,
)
from nucypher.crypto.ferveo.exceptions import FerveoKeyMismatch
from nucypher.crypto.powers import RitualisticPower
from nucypher.utilities.networking import LOOPBACK_ADDRESS
from tests.constants import (
    INSECURE_DEVELOPMENT_PASSWORD,
    TEST_ETH_PROVIDER_URI,
)
from tests.utils.ursula import select_test_port, start_pytest_ursula_services


@mock.patch('glob.glob', return_value=list())
def test_missing_configuration_file(_default_filepath_mock, click_runner):
    cmd_args = ("ursula", "run", "--domain", TEMPORARY_DOMAIN_NAME)
    result = click_runner.invoke(nucypher_cli, cmd_args, catch_exceptions=False)
    assert result.exit_code != 0
    configuration_type = UrsulaConfiguration.NAME
    assert NO_CONFIGURATIONS_ON_DISK.format(name=configuration_type.capitalize(),
                                            command=configuration_type) in result.output


@pt.inlineCallbacks
def test_ursula_startup(click_runner, mocker, accounts, testerchain):
    deploy_port = select_test_port()
    operator_address = accounts[-1].address

    mocker.patch.object(
        TACoApplicationAgent,
        "get_staking_provider_from_operator",
        return_value=accounts[-2].address,
    )
    mocker.patch.object(
        TACoChildApplicationAgent,
        "staking_provider_from_operator",
        return_value=accounts[-2].address,
    )
    mocker.patch.object(CoordinatorAgent, "set_provider_public_key", return_value=None)

    account = Account.from_key(private_key=accounts[operator_address].private_key)
    mocker.patch.object(Account, "create", return_value=account)

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
        operator_address,
        "--eth-endpoint",
        TEST_ETH_PROVIDER_URI,
        "--polygon-endpoint",
        TEST_ETH_PROVIDER_URI,
        "--signer",
        "memory://",
    )

    # Trigger a ferveo key mismatch
    mocker.patch.object(CoordinatorAgent, "get_provider_public_key", return_value=42)
    with pytest.raises(FerveoKeyMismatch):
        result = yield threads.deferToThread(
            click_runner.invoke,
            nucypher_cli,
            args,
            catch_exceptions=False,
            input=INSECURE_DEVELOPMENT_PASSWORD + "\n",
        )

    # Normal startup
    mocker.patch.object(RitualisticPower, "public_key", return_value=42)
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
