import pytest

from nucypher.blockchain.eth.actors import Operator
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.utilities.networking import UnknownIPAddress
from tests.constants import (
    FAKE_PASSWORD_CONFIRMED,
    MOCK_IP_ADDRESS,
    TEST_ETH_PROVIDER_URI,
    TEST_POLYGON_PROVIDER_URI,
)


@pytest.mark.skip("Hangs for unknown reason.  Refuses to exit.")
def test_ursula_startup_ip_checkup(click_runner, mocker):
    target = 'nucypher.cli.actions.configure.determine_external_ip_address'

    # Patch the get_external_ip call
    mocker.patch(target, return_value=MOCK_IP_ADDRESS)
    mocker.patch.object(UrsulaConfiguration, 'to_configuration_file', return_value=None)

    args = ('ursula', 'init', '--network', TEMPORARY_DOMAIN, '--eth-provider', TEST_ETH_PROVIDER_URI, '--payment-provider', TEST_POLYGON_PROVIDER_URI, '--force')
    user_input = FAKE_PASSWORD_CONFIRMED
    result = click_runner.invoke(nucypher_cli, args, catch_exceptions=False, input=user_input)
    assert result.exit_code == 0
    assert MOCK_IP_ADDRESS in result.output

    args = ('ursula', 'init', '--network', TEMPORARY_DOMAIN, '--force', '--eth-provider', TEST_ETH_PROVIDER_URI, '--payment-provider', TEST_POLYGON_PROVIDER_URI)
    result = click_runner.invoke(nucypher_cli, args, catch_exceptions=False, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 0

    # Patch get_external_ip call to error output
    mocker.patch(target, side_effect=UnknownIPAddress)
    args = ('ursula', 'init', '--network', TEMPORARY_DOMAIN, '--force', '--eth-provider', TEST_ETH_PROVIDER_URI, '--payment-provider', TEST_POLYGON_PROVIDER_URI)
    result = click_runner.invoke(nucypher_cli, args, catch_exceptions=True, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 1, result.output
    assert isinstance(result.exception, UnknownIPAddress)


@pytest.mark.skip("Depends on previous test")
def test_ursula_run_ip_checkup(
    testerchain, custom_filepath, click_runner, mocker, ursulas, monkeypatch
):

    # Mock IP determination
    target = 'nucypher.cli.actions.configure.determine_external_ip_address'
    mocker.patch(target, return_value=MOCK_IP_ADDRESS)

    # Mock Teacher Resolution
    from nucypher.characters.lawful import Ursula

    teacher = ursulas[0]
    mocker.patch.object(Ursula, 'from_teacher_uri', return_value=teacher)

    # Mock worker qualification
    staking_provider = ursulas[1]

    def set_staking_provider_address(operator, *args, **kwargs):
        operator.checksum_address = staking_provider.checksum_address
        return True
    monkeypatch.setattr(Operator, 'block_until_ready', set_staking_provider_address)

    # Setup
    teacher = ursulas[2]
    filename = UrsulaConfiguration.generate_filename()
    another_ursula_configuration_file_location = custom_filepath / filename

    # manual teacher
    run_args = ('ursula', 'run',
                '--dry-run',
                '--debug',
                '--config-file', str(another_ursula_configuration_file_location.absolute()),
                '--teacher', teacher.rest_url())
    result = click_runner.invoke(nucypher_cli, run_args, catch_exceptions=False, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 0, result.output

    # default teacher
    run_args = ('ursula', 'run',
                '--dry-run',
                '--debug',
                '--config-file', str(another_ursula_configuration_file_location.absolute()))
    result = click_runner.invoke(nucypher_cli, run_args, catch_exceptions=False, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 0, result.output

    ursulas.clear()
