"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


# WARNING This is not a mining script!
# you will not perform any re-encryptions, and you will not get paid.
# It might be (but might not be) useful for determining whether you have
# the proper dependencies and configuration to run an actual mining node.


from click.testing import CliRunner
from nucypher.cli.main import nucypher_cli


click_runner = CliRunner()

args = ['ursula', 'run',
        '--debug',             # Non-Interactive + Verbose
        '--rest-port', 11500,  # REST Server
        '--federated-only',    # Operating Mode
        '--dev',               # In-Memory
        '--lonely']            # Disable Seednode Learning

nucypher_cli.main(args=args, prog_name="nucypher-cli")
