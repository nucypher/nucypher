from click.testing import CliRunner
from nucypher.cli.main import nucypher_cli


click_runner = CliRunner()

args = ['ursula', 'run',
        '--rest-port', 11500,  # REST Server
        '--federated-only',    # Operating Mode
        '--dev',               # In-Memory
        '--debug',             # Non-Interactive + Verbose
        '--lonely']            # Disable Seednode Learning

nucypher_cli.main(args=args, prog_name="nucypher-cli")
