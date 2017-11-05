from kademlia.node import Node
from nkms.network.capabilities import ServerCapability


class NuCypherNode(Node):

    def __init__(self, id, ip=None, port=None, capabilities=None, capabilities_as_strings=[], *args, **kwargs):
        self.id = id
        self.ip = ip
        self.port = port
        self.long_id = int(id.hex(), 16)

        self.capabilities = capabilities or []

        for capability_name in capabilities_as_strings:
            self.capabilities.append(ServerCapability.from_name(capability_name))

    def can_store(self):
        for c in self.capabilities:
            if c.prohibits_storage:
                return False
        return True


class NetworkyStuff(object):

    def find_ursula(self, id, offer=None):
        pass