from kademlia.routing import RoutingTable


class NuCypherRoutingTable(RoutingTable):

    def addContact(self, node, seed_only=False):
        if seed_only:
            # We want to remember *not* to send values to this node, because it won't remember them.
            # TODO: What's the simplest upstream-compatible way to accomplish this?
            return super().addContact(node)
        else:
            return super().addContact(node)
