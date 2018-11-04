"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer


def test_nucypher_contract_compiled(testerchain):
    # Ensure that solidity smart contacts are available, post-compile.
    origin, *everybody_else = testerchain.interface.w3.eth.accounts

    token_contract_identifier = NucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)._contract_name
    assert token_contract_identifier in testerchain.interface._BlockchainInterface__raw_contract_cache
