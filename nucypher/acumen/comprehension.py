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

from constant_sorrow.constants import (
    UNVERIFIED,
    VERIFIED,
    UNAVAILABLE,
    SUSPICIOUS,
    UNSTAKED,
    INVALID,
    UNBONDED
)

NODE_BUCKETS = (

    #
    # Actively tracked nodes
    #
    VERIFIED,  # already verified
    UNVERIFIED,  # have not yet attempted to be verified

    #
    # Nodes that may no longer need to be tracked
    #
    UNAVAILABLE,  # node unresponsive during verification
    SUSPICIOUS,  # eg. SSL type errors, etc.
    UNSTAKED,  # no active stakes associated with node
    UNBONDED,  # node not bonded to a Staker
    INVALID  # generic node verification failure
)
