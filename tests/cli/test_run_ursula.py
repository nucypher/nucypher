from click.testing import CliRunner

from cli.main import cli


def test_run_lone_federated_ursula():
    runner = CliRunner()
    args = ['run_ursula',
            '--temp',
            '--federated-only',
            '--teacher-uri', 'localhost:5556']
    result_with_teacher = runner.invoke(cli, args, catch_exceptions=False)
    pass
