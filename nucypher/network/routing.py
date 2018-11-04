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
from kademlia.routing import RoutingTable


class NucypherRoutingTable(RoutingTable):

    def addContact(self, node, seed_only=False):
        if seed_only:
            # We want to remember *not* to send values to this node, because it won't remember them.
            # TODO: What's the simplest upstream-compatible way to accomplish this?
            return super().addContact(node)
        else:
            return super().addContact(node)
