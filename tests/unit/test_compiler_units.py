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

import pytest
from datetime import timedelta

from nucypher.blockchain.eth.sol.compile import DEFAULT_CONTRACT_VERSION, DEVDOC_VERSION_PATTERN
from hypothesis import given, example, settings
from hypothesis import strategies


# @settings(deadline=None)
# @given(strategies.text())
# @example("")
# def test_match_devdoc_version_string(string):
#     matches = VERSION_PATTERN.fullmatch(string=string)
#     assert matches is None


@example('|v1.2.3|')
@example('|v99.99.99|')
@example(f'|{DEFAULT_CONTRACT_VERSION}|')
@given(strategies.from_regex(DEVDOC_VERSION_PATTERN, fullmatch=True))
@settings(max_examples=5000)
def test_devdoc_regex_pattern(full_match):

    # Not empty
    assert full_match

    # Anchors
    assert full_match.startswith('|')   # start with version starting anchor
    assert full_match.endswith('|')

    # Max Size
    numbers_only = re.sub("[^0-9]", "", full_match)
    assert len(numbers_only) <= 6       # I mean really... who has a version with more than 6 numbers (v99.99.99)

    # "v"
    version_string = full_match[1:-1]
    assert version_string.startswith('v')       # start with version starting anchor
    assert version_string.count('v') == 1   # only one version indicator

    # 3 version parts
    assert version_string.count('.') == 2   # only two version part delimiters
    parts = version_string[1:]
    version_parts = parts.split('.')
    assert len(version_parts) == 3

    # Parts are numbers
    assert all(p.isdigit() for p in version_parts)
