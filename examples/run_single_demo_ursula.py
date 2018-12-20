from click.testing import CliRunner
from nucypher.cli.main import nucypher_cli
import sys

from nucypher.utilities.sandbox.constants import select_test_port

click_runner = CliRunner()

port = select_test_port()

try:
    learner_port = sys.argv[1]
except IndexError:
    learner_port = None

args = ['ursula', 'run',
        '--federated-only', '--rest-port', port,
        '--dev', '--debug']

if learner_port:
        args.extend(['--teacher-uri', 'https://127.0.0.1:{}'.format(int(learner_port))])

nucypher_cli.main(args=args or (), prog_name="nucypher-cli")
