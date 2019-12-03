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
import os
from os.path import dirname, abspath

from nucypher.blockchain.eth.deployers import NucypherTokenDeployer
from nucypher.blockchain.eth.sol.compile import SolidityCompiler, SourceDirs
from nucypher.utilities.sandbox.blockchain import TesterBlockchain


def test_nucypher_contract_compiled(testerchain, test_registry):
    # Ensure that solidity smart contacts are available, post-compile.
    origin, *everybody_else = testerchain.client.accounts

    token_contract_identifier = NucypherTokenDeployer(registry=test_registry, deployer_address=origin).contract_name
    assert token_contract_identifier in testerchain._raw_contract_cache
    token_data = testerchain._raw_contract_cache[token_contract_identifier]
    assert len(token_data) == 1
    assert "v0.0.0" in token_data


def test_multi_source_compilation(testerchain):
    solidity_compiler = SolidityCompiler(source_dirs=[
        (SolidityCompiler.default_contract_dir(), None),
        (SolidityCompiler.default_contract_dir(), {TesterBlockchain.TEST_CONTRACTS_DIR})
    ])
    interfaces = solidity_compiler.compile()

    # Remove AST because id in tree node depends on compilation scope
    for contract_name, contract_data in interfaces.items():
        for version, data in contract_data.items():
            data.pop("ast")
    raw_cache = testerchain._raw_contract_cache.copy()
    for contract_name, contract_data in raw_cache.items():
        for version, data in contract_data.items():
            data.pop("ast")
    assert interfaces == raw_cache


def test_multi_versions():
    base_dir = os.path.join(dirname(abspath(__file__)), "contracts", "multiversion")
    v1_dir = os.path.join(base_dir, "v1")
    v2_dir = os.path.join(base_dir, "v2")
    root_dir = SolidityCompiler.default_contract_dir()
    solidity_compiler = SolidityCompiler(source_dirs=[SourceDirs(root_dir, {v1_dir}),
                                                      SourceDirs(root_dir, {v2_dir})])
    interfaces = solidity_compiler.compile()
    assert "VersionTest" in interfaces
    contract_data = interfaces["VersionTest"]
    assert len(contract_data) == 2
    assert "v1.2.3" in contract_data
    assert "v1.1.4" in contract_data
    assert contract_data["v1.2.3"]["devdoc"] != contract_data["v1.1.4"]["devdoc"]
