import kademlia
from bytestring_splitter import BytestringSplitter
from constant_sorrow import default_constant_splitter, constants
from kademlia.node import Node
from kademlia.protocol import KademliaProtocol
from kademlia.utils import digest
from umbral.signing import Signature
from umbral.keys import UmbralPublicKey

from nucypher.crypto.api import keccak_digest
from nucypher.crypto.constants import PUBLIC_KEY_LENGTH, KECCAK_DIGEST_LENGTH
from nucypher.network.routing import NucypherRoutingTable

dht_value_splitter = default_constant_splitter + BytestringSplitter(Signature, (UmbralPublicKey, PUBLIC_KEY_LENGTH))
dht_with_hrac_splitter = dht_value_splitter + BytestringSplitter((bytes, KECCAK_DIGEST_LENGTH))


class NucypherHashProtocol(KademliaProtocol):
    def __init__(self, sourceNode, storage, ksize, *args, **kwargs):
        super().__init__(sourceNode, storage, ksize, *args, **kwargs)

        self.router = NucypherRoutingTable(self, ksize, sourceNode)
        self.illegal_keys_seen = []

        # TODO: This is the wrong way to do this.  See #227.
        self.treasure_maps = {}
        self.ursulas = {}

    def check_node_for_storage(self, node):
        try:
            return node.can_store()
        except AttributeError:
            return True

    async def callStore(self, nodeToAsk, key, value):
        # nodeToAsk = NucypherNode
        if self.check_node_for_storage(nodeToAsk):
            address = (nodeToAsk.ip, nodeToAsk.port)
            # TODO: encrypt `value` with public key of nodeToAsk
            store_future = self.store(address, self.sourceNode.id, key, value)
            result = await store_future
            success, data = self.handleCallResponse(result, nodeToAsk)
            return success, data
        else:
            return constants.NODE_HAS_NO_STORAGE, False

    def determine_legality_of_dht_key(self, signature, sender_pubkey_sig,
                                      message, hrac, dht_key, dht_value):

        # TODO: This function can use a once-over.
        # TODO: Push the logic of this if branch down.
        if dht_value[:8] == constants.BYTESTRING_IS_URSULA_IFACE_INFO:
            proper_key = digest(bytes(sender_pubkey_sig))
        else:
            proper_key = digest(
                keccak_digest(bytes(sender_pubkey_sig) + bytes(hrac)))

        verified = signature.verify(hrac, sender_pubkey_sig)

        if not verified or not proper_key == dht_key:
            # Hachidan Kiritsu, it's illegal!
            self.log.warning(
                "Got request to store illegal k/v: {} / {}".format(dht_key, dht_value))
            self.illegal_keys_seen.append(dht_key)
            return False
        else:
            return True

    def rpc_store(self, sender, nodeid, key, value):
        source = kademlia.node.Node(nodeid, sender[0], sender[1])
        self.welcomeIfNewNode(source)
        self.log.debug("got a store request from %s" % str(sender))

        # TODO: Why is this logic here?  This is madness.  See #172.
        if value.startswith(bytes(constants.BYTESTRING_IS_URSULA_IFACE_INFO)):
            header, signature, sender_pubkey_sig, message = dht_value_splitter(
                value, return_remainder=True)

            # TODO: TTL?
            hrac = keccak_digest(message)
            do_store = self.determine_legality_of_dht_key(signature, sender_pubkey_sig, message,
                                                          hrac, key, value)
        elif value.startswith(bytes(constants.BYTESTRING_IS_TREASURE_MAP)):
            header, signature, sender_pubkey_sig, hrac, message = dht_with_hrac_splitter(
                value, return_remainder=True)

            # TODO: TTL?
            do_store = self.determine_legality_of_dht_key(signature, sender_pubkey_sig, message,
                                                          hrac, key, value)
        else:
            self.log.info(
                "Got request to store bad k/v: {} / {}".format(key, value))
            do_store = False

        if do_store:
            self.log.info("Storing k/v: {} / {}".format(key, value))
            self.storage[key] = value
            if value.startswith(bytes(constants.BYTESTRING_IS_URSULA_IFACE_INFO)):
                self.ursulas[key] = value
            if value.startswith(bytes(constants.BYTESTRING_IS_TREASURE_MAP)):
                self.treasure_maps[key] = value

        return do_store


class NucypherSeedOnlyProtocol(NucypherHashProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def rpc_store(self, sender, nodeid, key, value):
        source = Node(nodeid, sender[0], sender[1])
        self.welcomeIfNewNode(source)
        self.log.debug(
            "got a store request from %s, but THIS VALUE WILL NOT BE STORED as this is a seed-only node." % str(
                sender))
        return True
