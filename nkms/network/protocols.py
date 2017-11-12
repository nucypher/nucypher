import msgpack

from kademlia.node import Node
from kademlia.protocol import KademliaProtocol
from kademlia.utils import digest
from nkms.crypto.api import keccak_digest
from nkms.crypto.constants import PUBKEY_SIG_LENGTH, HASH_DIGEST_LENGTH
from nkms.crypto.signature import Signature
from nkms.crypto.utils import BytestringSplitter
from nkms.network.constants import NODE_HAS_NO_STORAGE
from nkms.network.node import NuCypherNode
from nkms.network.routing import NuCypherRoutingTable

dht_value_splitter = BytestringSplitter(Signature, (bytes, PUBKEY_SIG_LENGTH), (bytes, HASH_DIGEST_LENGTH),
                                        return_remainder=True)


class NuCypherHashProtocol(KademliaProtocol):
    def __init__(self, sourceNode, storage, ksize, *args, **kwargs):
        super().__init__(sourceNode, storage, ksize, *args, **kwargs)
        self.router = NuCypherRoutingTable(self, ksize, sourceNode)
        self.illegal_keys_seen = []

    def check_node_for_storage(self, node):
        try:
            return node.can_store()
        except AttributeError:
            return True

    def rpc_ping(self, sender, nodeid, node_capabilities=[]):
        source = NuCypherNode(nodeid, sender[0], sender[1], capabilities_as_strings=node_capabilities)
        self.welcomeIfNewNode(source)
        return self.sourceNode.id

    async def callStore(self, nodeToAsk, key, value):
        # nodeToAsk = NuCypherNode
        if self.check_node_for_storage(nodeToAsk):
            address = (nodeToAsk.ip, nodeToAsk.port)
            # TODO: encrypt `value` with public key of nodeToAsk
            store_future = self.store(address, self.sourceNode.id, key, value)
            result = await store_future
            success, data = self.handleCallResponse(result, nodeToAsk)
            return success, data
        else:
            return NODE_HAS_NO_STORAGE, False

    def determine_legality_of_dht_key(self, signature, sender_pubkey_sig, message, hrac, dht_key, dht_value):
        proper_key = digest(keccak_digest(bytes(sender_pubkey_sig) + bytes(hrac)))

        # TODO: This try block is not the right approach - a Ciphertext class can resolve this instead.
        try:
            # Ursula uaddr scenario
            verified = signature.verify(hrac, sender_pubkey_sig)
        except Exception as e:
            # trmap scenario
            verified = signature.verify(msgpack.dumps(message), sender_pubkey_sig)

        if not verified or not proper_key == dht_key:
            self.log.warning("Got request to store illegal k/v: {} / {}".format(dht_key, dht_value))
            self.illegal_keys_seen.append(dht_key)
            return False
        else:
            return True

    def rpc_store(self, sender, nodeid, key, value):
        source = NuCypherNode(nodeid, sender[0], sender[1])
        self.welcomeIfNewNode(source)
        self.log.debug("got a store request from %s" % str(sender))

        if value.startswith(b"uaddr") or value.startswith(b"trmap"):
            signature, sender_pubkey_sig, hrac, message = dht_value_splitter(value[5::])

            # extra_info is a hash of the policy_group.id in the case of a treasure map, or a TTL in the case
            # of an Ursula interface.  TODO: Decide whether to keep this notion and, if so, use the TTL.
            do_store = self.determine_legality_of_dht_key(signature, sender_pubkey_sig, message, hrac, key, value)
        else:
            self.log.info("Got request to store bad k/v: {} / {}".format(key, value))
            do_store = False

        if do_store:
            self.log.info("Storing k/v: {} / {}".format(key, value))
            self.storage[key] = value

        return do_store


class NuCypherSeedOnlyProtocol(NuCypherHashProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def rpc_store(self, sender, nodeid, key, value):
        source = Node(nodeid, sender[0], sender[1])
        self.welcomeIfNewNode(source)
        self.log.debug(
            "got a store request from %s, but THIS VALUE WILL NOT BE STORED as this is a seed-only node." % str(
                sender))
        return True
