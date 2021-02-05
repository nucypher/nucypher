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


import re
from cytoolz.dicttoolz import merge
from typing import Dict

from nucypher.blockchain.eth.sol.compile.constants import DEFAULT_VERSION_STRING, SOLC_LOGGER
from nucypher.blockchain.eth.sol.compile.exceptions import CompilationError, ProgrammingError
from nucypher.blockchain.eth.sol.compile.types import VersionedContractOutputs, CompiledContractOutputs

# RE pattern for matching solidity source compile version specification in devdoc details.
DEVDOC_VERSION_PATTERN = re.compile(r"""
\A            # Anchor must be first
\|            # Anchored pipe literal at beginning of version definition
(             # Start Inner capture group
v             # Capture version starting from symbol v
\d+           # At least one digit of major version
\.            # Digits splitter
\d+           # At least one digit of minor version
\.            # Digits splitter
\d+           # At least one digit of patch
)             # End of capturing
\|            # Anchored end of version definition | 
\Z            # Anchor must be the end of the match
""", re.VERBOSE)

# simplified version of pattern to extract metadata hash from bytecode
# see https://docs.soliditylang.org/en/latest/metadata.html#encoding-of-the-metadata-hash-in-the-bytecode
METADATA_HASH_PATTERN = re.compile(r"""
a2
64
69706673    # 'i' 'p' 'f' 's'
58
22
\w{68}      # 34 bytes IPFS hash
64
736f6c63    # 's' 'o' 'l' 'c'    
43
\w{6}       # <3 byte version encoding>
0033
""", re.VERBOSE)


def extract_version(compiled_contract_outputs: dict) -> str:
    """
    Returns the source specified version of a compiled solidity contract.
    Examines compiled contract output for devdoc details and perform a fulltext search for a source version specifier.
    """
    try:
        devdoc: Dict[str, str] = compiled_contract_outputs['devdoc']
    except KeyError:
        # Edge Case
        # ---------
        # If this block is reached, the compiler did not produce results for devdoc at all.
        # Ensure 'devdoc' is listed in `CONTRACT_OUTPUTS` and that solc is the latest version.
        raise CompilationError(f'Solidity compiler did not output devdoc.'
                               f'Check the contract output compiler settings.')
    else:
        title = devdoc.get('title', '')

    try:
        devdoc_details: str = devdoc['details']
    except KeyError:
        # This is acceptable behaviour, most likely an un-versioned contract
        SOLC_LOGGER.debug(f'No solidity source version specified.')
        return DEFAULT_VERSION_STRING

    # RE Full Match
    raw_matches = DEVDOC_VERSION_PATTERN.fullmatch(devdoc_details)

    # Positive match(es)
    if raw_matches:
        matches = raw_matches.groups()
        if len(matches) != 1:  # sanity check
            # Severe Edge Case
            # -----------------
            # "Impossible" situation: If this block is ever reached,
            # the regular expression matching contract versions
            # inside devdoc details matched multiple groups (versions).
            # If you are here, and this exception is raised - do not panic!
            # This most likely means there is a programming error
            # in the `VERSION_PATTERN` regular expression or the surrounding logic.
            raise ProgrammingError(f"Multiple version matches in {title} devdoc.")
        version = matches[0]  # good match
        return version        # OK
    else:
        # Negative match: Devdoc included without a version
        SOLC_LOGGER.debug(f"Contract {title} not versioned.")
        return DEFAULT_VERSION_STRING


def validate_merge(existing_version: CompiledContractOutputs,
                   new_version: CompiledContractOutputs,
                   version_specifier: str) -> None:
    """Compare with incoming compiled contract data"""
    new_title = new_version['devdoc'].get('title')
    versioned: bool = version_specifier != DEFAULT_VERSION_STRING
    if versioned and new_title:
        existing_title = existing_version['devdoc'].get('title')
        if existing_title == new_title:  # This is the same contract
            # TODO this code excludes hash of metadata, it's not perfect because format of metadata could change
            # ideally use a proper CBOR parser
            existing_bytecode = METADATA_HASH_PATTERN.sub('', existing_version['evm']['bytecode']['object'])
            new_bytecode = METADATA_HASH_PATTERN.sub('', new_version['evm']['bytecode']['object'])
            if not existing_bytecode == new_bytecode:
                message = f"Two solidity sources ({new_title}, {existing_title}) specify version '{version_specifier}' " \
                          "but have different compiled bytecode. Ensure that the devdoc version is " \
                          "accurately updated before trying again."
                raise CompilationError(message)


def merge_contract_sources(*compiled_sources):
    return merge(*compiled_sources)  # TODO: Handle file-level output aggregation


def merge_contract_outputs(*compiled_versions) -> VersionedContractOutputs:
    versioned_outputs = dict()

    for bundle in compiled_versions:

        for contract_outputs in bundle:
            version = extract_version(compiled_contract_outputs=contract_outputs)

            try:
                existing_version = versioned_outputs[version]

            except KeyError:
                # New Version Entry
                bytecode = METADATA_HASH_PATTERN.sub('', contract_outputs['evm']['bytecode']['object'])
                if len(bytecode) > 0:
                    for existing_version, existing_contract_outputs in versioned_outputs.items():
                        existing_bytecode = METADATA_HASH_PATTERN.sub('', existing_contract_outputs['evm']['bytecode']['object'])
                        if bytecode == existing_bytecode:
                            raise CompilationError(
                                f"Two solidity sources compiled identical bytecode for versions {version} and {existing_version}. "
                                "Ensure the correct solidity paths are targeted for compilation.")
                versioned_outputs[version] = contract_outputs

            else:
                # Existing Version Update
                validate_merge(existing_version=existing_version,
                               new_version=contract_outputs,
                               version_specifier=version)
                versioned_outputs[version] = contract_outputs

    return VersionedContractOutputs(versioned_outputs)
