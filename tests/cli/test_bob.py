from nucypher.cli.main import nucypher_cli


# TODO: test can probably be removed (--dev is not a valid option for `init`)
def test_bob_cannot_init_with_dev_flag(click_runner):
    init_args = ('bob', 'init',
                 '--federated-only',
                 '--dev')
    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False)
    assert result.exit_code == 2
    assert 'no such option: --dev' in result.output, 'Missing or invalid error message was produced.'
