from nucypher.cli.main import nucypher_cli
from umbral.keys import UmbralPrivateKey


def test_enrico_encrypt(click_runner):
    policy_encrypting_key = UmbralPrivateKey.gen_key().get_pubkey().to_bytes().hex()
    encrypt_args = ('enrico', 'encrypt',
                    '--message', 'to be or not to be',
                    '--policy-encrypting-key', policy_encrypting_key)
    result = click_runner.invoke(nucypher_cli, encrypt_args, catch_exceptions=False)

    assert result.exit_code == 0
    assert policy_encrypting_key in result.output
    assert "message_kit" in result.output
    assert "signature" in result.output


def test_enrico_control_starts(click_runner):
    policy_encrypting_key = UmbralPrivateKey.gen_key().get_pubkey().to_bytes().hex()
    run_args = ('enrico', 'run',
                '--policy-encrypting-key', policy_encrypting_key,
                '--dry-run')

    result = click_runner.invoke(nucypher_cli, run_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert policy_encrypting_key in result.output
