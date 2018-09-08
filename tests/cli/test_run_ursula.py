from click.testing import CliRunner

from cli.main import cli


def test_run_federated_ursulas():
    runner = CliRunner()

    # result = runner.invoke(cli,
    #                        ['run_ursula', '--federated-only', '--rest-port', '5431'],
    #                        catch_exceptions=False)

    result_with_teacher = runner.invoke(cli,
                                        ['run_ursula', '--federated-only',
                                         '--teacher-uri', 'localhost:5556'],
                                          catch_exceptions=False)


