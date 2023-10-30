from nucypher.blockchain.eth.actors import Operator
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from tests.constants import FAKE_PASSWORD_CONFIRMED, MOCK_IP_ADDRESS


def mock_ursula_run(mocker, ursulas, monkeypatch, ursula_test_config, mock_prometheus):
    # Mock IP determination
    target = "nucypher.cli.actions.configure.determine_external_ip_address"
    mocker.patch(target, return_value=MOCK_IP_ADDRESS)

    ursula_test_config.rest_host = MOCK_IP_ADDRESS

    # Mock worker qualification
    staking_provider = ursulas[1]

    def set_staking_provider_address(operator):
        operator.checksum_address = staking_provider.checksum_address
        return True

    monkeypatch.setattr(Operator, "block_until_ready", set_staking_provider_address)

    # Mock Ursula configuration
    mocker.patch.object(
        UrsulaConfiguration, "from_configuration_file", return_value=ursula_test_config
    )

    # Resetting start_prometheus_exporter mock just in case it was called in other test
    mock_prometheus.reset_mock()


def test_ursula_cli_prometheus(
    click_runner,
    mocker,
    ursulas,
    monkeypatch,
    ursula_test_config,
    tempfile_path,
    mock_prometheus,
):
    mock_ursula_run(mocker, ursulas, monkeypatch, ursula_test_config, mock_prometheus)

    run_args = (
        "ursula",
        "run",
        "--dry-run",
        "--debug",
        "--config-file",
        str(tempfile_path.absolute()),
    )

    result = click_runner.invoke(
        nucypher_cli, run_args, input=FAKE_PASSWORD_CONFIRMED, catch_exceptions=False
    )

    assert result.exit_code == 0, result.output
    assert (
        f"✓ Prometheus Exporter http://{MOCK_IP_ADDRESS}:9101/metrics" in result.output
    ), "CLI didn't print Prometheus exporter check"

    mock_prometheus.assert_called_once()
    assert (
        mock_prometheus.call_args.kwargs["prometheus_config"].port == 9101
    ), "Wrong port set in prometheus_config"
    assert (
        mock_prometheus.call_args.kwargs["prometheus_config"].listen_address == ""
    ), "Wrong listen address set in prometheus_config"
    assert (
        mock_prometheus.call_args.kwargs["prometheus_config"].collection_interval == 90
    ), "Wrong collection interval set in prometheus_config"
    assert (
        mock_prometheus.call_args.kwargs["prometheus_config"].start_now is False
    ), "Wrong value for start_now in prometheus_config"


def test_ursula_cli_prometheus_metrics_port(
    click_runner,
    mocker,
    ursulas,
    monkeypatch,
    ursula_test_config,
    tempfile_path,
    mock_prometheus,
):
    port = 6666

    mock_ursula_run(mocker, ursulas, monkeypatch, ursula_test_config, mock_prometheus)

    run_args = (
        "ursula",
        "run",
        "--dry-run",
        "--debug",
        "--config-file",
        str(tempfile_path.absolute()),
        "--metrics-port",
        str(port),
    )

    result = click_runner.invoke(
        nucypher_cli, run_args, input=FAKE_PASSWORD_CONFIRMED, catch_exceptions=False
    )

    assert result.exit_code == 0, result.output
    assert (
        f"✓ Prometheus Exporter http://{MOCK_IP_ADDRESS}:{port}/metrics"
        in result.output
    ), "CLI didn't print Prometheus exporter check"

    mock_prometheus.assert_called_once()
    assert (
        mock_prometheus.call_args.kwargs["prometheus_config"].port == port
    ), "Wrong port set in prometheus_config"
    assert (
        mock_prometheus.call_args.kwargs["prometheus_config"].listen_address == ""
    ), "Wrong listen address set in prometheus_config"
    assert (
        mock_prometheus.call_args.kwargs["prometheus_config"].collection_interval == 90
    ), "Wrong collection interval set in prometheus_config"
    assert (
        mock_prometheus.call_args.kwargs["prometheus_config"].start_now is False
    ), "Wrong value for start_now in prometheus_config"
