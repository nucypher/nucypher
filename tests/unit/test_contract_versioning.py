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
from hypothesis import given, example, settings
from hypothesis import strategies

from nucypher.blockchain.eth.sol.compile.aggregation import DEVDOC_VERSION_PATTERN
from nucypher.blockchain.eth.sol.compile.constants import DEFAULT_VERSION_STRING


@example('|v1.2.3|')
@example('|v99.99.99|')
@example(f'|{DEFAULT_VERSION_STRING}|')
@given(strategies.from_regex(DEVDOC_VERSION_PATTERN, fullmatch=True))
@settings(max_examples=50)
def test_devdoc_regex_pattern(full_match):

    # Not empty
    assert full_match, 'Devdoc regex pattern matched an empty value: "{version_string}"'

    # Anchors
    assert full_match.startswith('|'), 'Version string does not end in "|" delimiter: "{version_string}"'
    assert full_match.endswith('|'), 'Version string does not end in "|" delimiter: "{version_string}"'

    # "v" specifier
    version_string = full_match[1:-1]
    assert version_string.startswith('v'), 'Version string does not start with "v": "{version_string}"'
    assert version_string.count('v') == 1, 'Version string contains more than one "v": "{version_string}"'

    # Version parts
    assert version_string.count('.') == 2, f'Version string has more than two periods: "{version_string}"'
    parts = version_string[1:]
    version_parts = parts.split('.')
    assert len(version_parts) == 3, f'Version string has more than three parts: "{version_string}"'

    # Parts are numbers
    assert all(p.isdigit() for p in version_parts), f'Non-digit found in version string: "{version_string}"'
