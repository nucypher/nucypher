import pytest
from nucypher.cli.main import nucypher_cli


def test_device_cli_backend_errors(click_runner):
    with pytest.raises(RuntimeError):
        device_args = ('device', 'init')
        click_runner.invoke(nucypher_cli, device_args,
                            catch_exceptions=False)

    # TODO: When multiple device support is added, add test to show you can't
    # call `nucypher device` with multiple device flags.

    device_args = ('device', 'bad arg')
    res = click_runner.invoke(nucypher_cli, device_args,
                              catch_exceptions=False)
    assert res.exit_code == 2


def test_device_cli_init_trezor(click_runner, mock_trezorlib):
    trezor_init_args = ('device', 'init', '--trezor')

    with pytest.raises(NotImplementedError):
        click_runner.invoke(nucypher_cli, trezor_init_args,
                            catch_exceptions=False)
