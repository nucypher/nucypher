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

from pathlib import Path

from nucypher.blockchain.eth.sol.compile.compile import multiversion_compile
from nucypher.blockchain.eth.sol.compile.constants import DEFAULT_VERSION_STRING
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer


def test_nucypher_contract_compiled(testerchain, test_registry):
    """Ensure that solidity smart contacts are available, post-compile."""
    origin, *everybody_else = testerchain.client.accounts

    token_contract_identifier = NucypherTokenDeployer(registry=test_registry, deployer_address=origin).contract_name
    assert token_contract_identifier in testerchain._raw_contract_cache
    token_data = testerchain._raw_contract_cache[token_contract_identifier]
    assert len(token_data) == 1
    assert DEFAULT_VERSION_STRING in token_data


def test_multi_source_compilation(testerchain):
    # TODO: Remove AST because id in tree node depends on compilation scope <<< Still relevant?
    interfaces = multiversion_compile(solidity_source_dirs=testerchain.SOURCES)
    raw_cache = testerchain._raw_contract_cache.copy()
    assert interfaces == raw_cache


def test_multi_versions():
    base_dir = Path(__file__).parent / "contracts" / "multiversion"
    v1_dir, v2_dir = base_dir / "v1", base_dir / "v2"
    interfaces = multiversion_compile(solidity_source_dirs=(v1_dir, v2_dir))
    assert "VersionTest.sol" in interfaces['contracts']
    contract_data = interfaces['contracts']["VersionTest.sol"]
    assert len(contract_data) == 2
    assert "v1.2.3" in contract_data
    assert "v1.1.4" in contract_data
    assert contract_data["v1.2.3"]["devdoc"]['details'] != contract_data["v1.1.4"]["devdoc"]['details']
