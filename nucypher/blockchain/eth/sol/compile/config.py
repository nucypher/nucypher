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


from typing import List, Dict

from nucypher.blockchain.eth.sol.compile.constants import (
    CONTRACTS, ZEPPELIN, ARAGON
)
from nucypher.blockchain.eth.sol.compile.types import CompilerConfiguration

"""
Standard "JSON I/O" Compiler Config Reference:

Input: https://solidity.readthedocs.io/en/latest/using-the-compiler.html#input-description
Output: https://solidity.readthedocs.io/en/latest/using-the-compiler.html#output-description

WARNING: Do not change these values unless you know what you are doing.
"""


# Debug
# -----
# How to treat revert (and require) reason strings.
# "default", "strip", "debug" and "verboseDebug".
# "default" does not inject compiler-generated revert strings and keeps user-supplied ones.
# "strip" removes all revert strings (if possible, i.e. if literals are used) keeping side-effects
# "debug" injects strings for compiler-generated internal reverts, implemented for ABI encoders V1 and V2 for now.
# "verboseDebug" even appends further information to user-supplied revert strings (not yet implemented)
# DEBUG = 'default'

# Source code language. Currently supported are "Solidity" and "Yul".
LANGUAGE: str = 'Solidity'

# Version of the EVM to compile for. Affects type checking and code generation.
EVM_VERSION: str = 'berlin'

# File level compiler outputs (needs empty string as contract name):
FILE_OUTPUTS: List[str] = [
    'ast'          # AST of all source files
    # 'legacyAST'  # legacy AST of all source files
]

# Contract level (needs the contract name or "*")
CONTRACT_OUTPUTS: List[str] = [

    'abi',                            # ABI
    'devdoc',                         # Developer documentation (natspec)
    'userdoc',                        # User documentation (natspec)
    'evm.bytecode.object',            # Bytecode object

    # 'metadata',                     #  Metadata
    # 'ir',                           #  Yul intermediate representation of the code before optimization
    # 'irOptimized',                  #  Intermediate representation after optimization
    # 'storageLayout',                #  Slots, offsets and types of the contract's state variables.
    # 'evm.assembly',                 # New assembly format
    # 'evm.legacyAssembly',           # Old-style assembly format in JSON
    # 'evm.bytecode.opcodes',         # Opcodes list
    # 'evm.bytecode.sourceMap',       # Source mapping (useful for debugging)
    # 'evm.bytecode.linkReferences',  # Link references (if unlinked object)
    # 'evm.deployedBytecode*',        # Deployed bytecode (has all the options that evm.bytecode has)
    # 'evm.deployedBytecode.immutableReferences', # Map from AST ids to bytecode ranges that reference immutables
    # 'evm.methodIdentifiers',        # The list of function hashes
    # 'evm.gasEstimates',             # Function gas estimates
    # 'ewasm.wast',                   # eWASM S-expressions format (not supported at the moment)
    # 'ewasm.wasm',                   # eWASM binary format (not supported at the moment)
]

# Optimizer Details - Switch optimizer components on or off in detail.
# The "enabled" switch above provides two defaults which can be tweaked here (yul, and ...).
OPTIMIZER_DETAILS = dict(
    peephole=True,            # The peephole optimizer is always on if no details are given (switch it off here).
    jumpdestRemover=True,     # The unused jumpdest remover is always on if no details are given (switch it off here).
    orderLiterals=False,      # Sometimes re-orders literals in commutative operations.
    deduplicate=False,        # Removes duplicate code blocks
    cse=False,                # Common subexpression elimination, Most complicated step but provides the largest gain.
    constantOptimizer=False,  # Optimize representation of literal numbers and strings in code.

    # The new Yul optimizer. Mostly operates on the code of ABIEncoderV2 and inline assembly.
    # It is activated together with the global optimizer setting and can be deactivated here.
    # Before Solidity 0.6.0 it had to be activated through this switch.  Also see 'yulDetails options'.
    yul=True
)

# Optimize for how many times you intend to run the code.
# Lower values will optimize more for initial deployment cost, higher
# values will optimize more for high-frequency usage.
OPTIMIZER_RUNS = 200

OPTIMIZER_SETTINGS = dict(
    enabled=True,
    runs=OPTIMIZER_RUNS,
    # details=OPTIMIZER_DETAILS  # Optional - If "details" is given, "enabled" can be omitted.
)

# Complete compiler settings
COMPILER_SETTINGS: Dict = dict(
    optimizer=OPTIMIZER_SETTINGS,
    evmVersion=EVM_VERSION,
    outputSelection={"*": {"*": CONTRACT_OUTPUTS, "": FILE_OUTPUTS}},  # all contacts(*), all files("")
)

REMAPPINGS: List = [CONTRACTS, ZEPPELIN, ARAGON]

# Base configuration for programmatic usage
BASE_COMPILER_CONFIGURATION = CompilerConfiguration(
    language=LANGUAGE,
    settings=COMPILER_SETTINGS,
    # sources and remappings added dynamically during runtime
)
