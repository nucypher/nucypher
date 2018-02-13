from kademlia.node import Node

from nkms.crypto.constants import CFRAG_LENGTH
from nkms.crypto.utils import RepeatingBytestringSplitter
from nkms.network.capabilities import ServerCapability
from umbral.fragments import CapsuleFrag


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

    class NotEnoughQualifiedUrsulas(Exception):
        pass

    def find_ursula(self, id, offer=None):
        pass

    def reencrypt(self, work_order):
        ursula = self.get_ursula_by_id(work_order.ursula_id)
        ursula_rest_response = self.send_work_order_payload_to_ursula(work_order, ursula)
        cfrags = RepeatingBytestringSplitter((CapsuleFrag, CFRAG_LENGTH))(ursula_rest_response.content)
        work_order.complete(cfrags)  # TODO: We'll do verification of Ursula's signature here.  #141
        return cfrags

    def get_competitive_rate(self):
        return NotImplemented
