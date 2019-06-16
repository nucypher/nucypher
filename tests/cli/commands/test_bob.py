from nucypher.cli.main import nucypher_cli


def test_bob_cannot_init_with_dev_flag(click_runner):
    init_args = ('bob', 'init',
                 '--federated-only',
                 '--dev')
    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False)
    assert result.exit_code == 2
    assert 'Cannot create a persistent development character' in result.output, 'Missing or invalid error message was produced.'
