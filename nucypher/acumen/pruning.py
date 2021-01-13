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

from collections import Counter

import maya
from typing import Optional, Callable


def accept_node(node: "Teacher", reset: bool = False) -> bool:
    """
    Return True to keep a node or False to Erase
    NOTE: This function *must* return a boolean to operate properly.
    """
    return True


def reject_node(node: "Teacher", reset: bool = False) -> bool:
    """Indicate a node can be deleted now."""
    return False


def construct_node_stalecheck(max_seconds: int, start_time: Optional[maya.MayaDT] = None) -> Callable:
    start_time = start_time or maya.now()

    def check(node: "Teacher", reset: bool = False) -> bool:
        # if reset:
        #     start_time = maya.now()
        #     return True
        delta = start_time - node.last_seen
        return delta.seconds() > max_seconds

    return check


def construct_node_max_attempts(max_attempts: int) -> Callable:
    attempts = Counter()

    def check(node: "Teacher", reset: bool = False) -> bool:
        if reset:
            del attempts[node.checksum_address]
            return True
        attempts[node.checksum_address] += 1
        if attempts[node.checksum_address] > max_attempts:
            del attempts[node.checksum_address]  # stop tracking.
            return False
        return True

    return check
