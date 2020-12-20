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


from jsonschema2rst.parser import _traverse_bfs, _node2rst
from jsonschema2rst.rst_utils import RST_DIRECTIVES
from jsonschema2rst.tree_node import TreeNode

from nucypher.blockchain.eth.sol.compile.compile import multiversion_compile
from nucypher.blockchain.eth.sol.compile.constants import SOLIDITY_SOURCE_ROOT
from nucypher.blockchain.eth.sol.compile.types import SourceBundle
from nucypher.config.constants import BASE_DIR
from nucypher.utilities.logging import GlobalLoggerSettings


CONTRACTS = ['StakingEscrow',
             'PolicyManager',
             'WorkLock',
             'Adjudicator',
             'Dispatcher',
             'Upgradeable',
             'TokenRecipient',
             'NuCypherToken',
             'StakingInterface',
             'StakingInterfaceRouter',
             'AbstractStakingContract',
             'InitializableStakingContract',
             'PoolingStakingContract',
             'WorkLockPoolingContract']


def merge_and_update(source, destination):
    """Update values in source dictionary and merge it to the destination dictionary"""

    for key, value in source.items():
        if isinstance(value, dict):
            destination[key] = merge_and_update(value, destination.get(key, {}))
        else:
            # | symbol causes warnings in docs compilation
            # doubles ` symbol to make it as code piece in rst
            value = value.replace('`', '``').replace('|', '') if isinstance(value, str) else value
            destination[key] = value
    return destination


def generate_doc() -> None:
    """Compile solidity contracts, extract json docs and generate rst files from them"""

    GlobalLoggerSettings.start_console_logging()

    bundle = SourceBundle(base_path=SOLIDITY_SOURCE_ROOT)
    contracts = multiversion_compile(source_bundles=[bundle])

    base_path = BASE_DIR / 'docs' / 'source' / 'contracts_api'
    base_path.mkdir(exist_ok=True)

    patch()
    for contract, data in contracts.items():
        if contract not in CONTRACTS:
            continue

        no_version = next(iter(data.values()))
        docs = merge_and_update(no_version["userdoc"], dict())
        docs = merge_and_update(no_version["devdoc"], docs)

        rst = schema2rst(docs, "kind,version,title", contract)
        with open(base_path / f"{contract}.rst", 'w') as file:
            file.write(rst)


def schema2rst(data, excluded_key, tree_name):
    """Mimics parser.schema2rst method with string input parameters"""

    tree = TreeNode(tree_name)

    rst = RST_DIRECTIVES
    TreeNode.dict2tree(data, tree, excluded_key)
    rst += _traverse_bfs(tree, _node2rst)
    return rst


def patch():
    """Remove putting quotes in strings while handling json schema"""

    def _literal(val):
        return val

    import jsonschema2rst
    jsonschema2rst.rst_utils.literal = _literal


if __name__ == '__main__':
    generate_doc()
