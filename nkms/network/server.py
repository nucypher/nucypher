import asyncio
import binascii
import random

from apistar import http
from apistar.http import Response
from kademlia.crawling import NodeSpiderCrawl
from kademlia.network import Server
from kademlia.utils import digest
from sqlalchemy.exc import IntegrityError

from nkms.crypto.kits import MessageKit
from nkms.crypto.powers import EncryptingPower, SigningPower
from nkms.crypto.utils import BytestringSplitter
from nkms.network.capabilities import SeedOnly, ServerCapability
from nkms.network.node import NuCypherNode
from nkms.network.protocols import NuCypherSeedOnlyProtocol, NuCypherHashProtocol
from nkms.network.storage import SeedOnlyStorage
from umbral import pre
from umbral.fragments import KFrag


class NuCypherDHTServer(Server):
    protocol_class = NuCypherHashProtocol
    capabilities = ()
    digests_set = 0

    def __init__(self, ksize=20, alpha=3, id=None, storage=None, *args, **kwargs):
        super().__init__(ksize=20, alpha=3, id=None, storage=None, *args, **kwargs)
        self.node = NuCypherNode(id or digest(
            random.getrandbits(255)))  # TODO: Assume that this can be attacked to get closer to desired kFrags.

    def serialize_capabilities(self):
        return [ServerCapability.stringify(capability) for capability in self.capabilities]

    async def bootstrap_node(self, addr):
        """
        Announce node including capabilities
        """
        result = await self.protocol.ping(addr, self.node.id, self.serialize_capabilities())
        return NuCypherNode(result[1], addr[0], addr[1]) if result[0] else None

    async def set_digest(self, dkey, value):
        """
        Set the given SHA1 digest key (bytes) to the given value in the network.

        Returns True if a digest was in fact set.
        """
        node = self.node_class(dkey)

        nearest = self.protocol.router.findNeighbors(node)
        if len(nearest) == 0:
            self.log.warning("There are no known neighbors to set key %s" % dkey.hex())
            return False

        spider = NodeSpiderCrawl(self.protocol, node, nearest, self.ksize, self.alpha)
        nodes = await spider.find()

        self.log.info("setting '%s' on %s" % (dkey.hex(), list(map(str, nodes))))

        # if this node is close too, then store here as well
        if self.node.distanceTo(node) < max([n.distanceTo(node) for n in nodes]):
            self.storage[dkey] = value
        ds = []
        for n in nodes:
            _disposition, value_was_set = await self.protocol.callStore(n, dkey, value)
            if value_was_set:
                self.digests_set += 1
            ds.append(value_was_set)
        # return true only if at least one store call succeeded
        return any(ds)

    def get_now(self, key):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.get(bytes(key)))

    async def set(self, key, value):
        """
        Set the given string key to the given value in the network.
        """
        self.log.debug("setting '%s' = '%s' on network" % (key, value))
        key = digest(bytes(key))
        return await self.set_digest(key, value)


class NuCypherSeedOnlyDHTServer(NuCypherDHTServer):
    protocol_class = NuCypherSeedOnlyProtocol
    capabilities = (SeedOnly(),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.storage = SeedOnlyStorage()


class ProxyRESTServer(object):

    def get_signing_and_encrypting_public_keys(self):
        """
        REST endpoint for getting both signing and encrypting public keys.
        """
        return Response(
            content=bytes(self.stamp) + bytes(self.public_key(EncryptingPower)),
            content_type="application/octet-stream")

    def consider_contract(self, hrac_as_hex, request: http.Request):
        # TODO: This actually needs to be a REST endpoint, with the payload
        # carrying the kfrag hash separately.
        from nkms.policy.models import Contract
        contract, deposit_as_bytes = \
            BytestringSplitter(Contract)(request.body, return_remainder=True)
        contract.deposit = deposit_as_bytes

        # contract_to_store = {  # TODO: This needs to be a datastore - see #127.
        #     "alice_pubkey_sig":
        #     "deposit": contract.deposit,
        #     # TODO: Whatever type "deposit" ends up being, we'll need to
        #     # serialize it here.  See #148.
        #     "expiration": contract.expiration,
        # }
        self.keystore.add_policy_contract(contract.expiration.datetime(),
                                          contract.deposit,
                                          hrac=contract.hrac.hex().encode(),
                                          alice_pubkey_sig=contract.alice.stamp
                                          )
        # TODO: Make the rest of this logic actually work - do something here
        # to decide if this Contract is worth accepting.
        return Response(
            b"This will eventually be an actual acceptance of the contract.",
            content_type="application/octet-stream")

    def set_policy(self, hrac_as_hex, request: http.Request):
        """
        REST endpoint for setting a kFrag.
        TODO: Instead of taking a Request, use the apistar typing system to type
            a payload and validate / split it.
        TODO: Validate that the kfrag being saved is pursuant to an approved
            Policy (see #121).
        """
        hrac = binascii.unhexlify(hrac_as_hex)
        policy_message_kit = MessageKit.from_bytes(request.body)
        # group_payload_splitter = BytestringSplitter(PublicKey)
        # policy_payload_splitter = BytestringSplitter((KFrag, KFRAG_LENGTH))

        alice = self._alice_class.from_public_keys((SigningPower, policy_message_kit.alice_pubkey))

        verified, cleartext = self.verify_from(
            alice, policy_message_kit,
            decrypt=True, signature_is_on_cleartext=True)

        if not verified:
            # TODO: What do we do if the Policy isn't signed properly?
            pass
        #
        # alices_signature, policy_payload =\
        #     BytestringSplitter(Signature)(cleartext, return_remainder=True)

        # TODO: If we're not adding anything else in the payload, stop using the
        # splitter here.
        # kfrag = policy_payload_splitter(policy_payload)[0]
        kfrag = KFrag.from_bytes(cleartext)

        # TODO: Query stored Contract and reconstitute
        policy_contract = self.keystore.get_policy_contract(hrac_as_hex.encode())
        # contract_details = self._contracts[hrac.hex()]

        if policy_contract.alice_pubkey_sig.key_data != alice.stamp:
            raise self._alice_class.SuspiciousActivity

        # contract = Contract(alice=alice, hrac=hrac,
        #                     kfrag=kfrag, expiration=policy_contract.expiration)

        try:
            # TODO: Obviously we do this lower-level.
            policy_contract.k_frag = bytes(kfrag)
            self.keystore.session.commit()

        except IntegrityError:
            raise
            # Do something appropriately RESTful (ie, 4xx).

        return  # TODO: Return A 200, with whatever policy metadata.

    def reencrypt_via_rest(self, hrac_as_hex, request: http.Request):
        from nkms.policy.models import WorkOrder  # Avoid circular import
        hrac = binascii.unhexlify(hrac_as_hex)
        work_order = WorkOrder.from_rest_payload(hrac, request.body)
        kfrag_bytes = self.keystore.get_policy_contract(hrac.hex().encode()).k_frag  # Careful!  :-)
        # TODO: Push this to a lower level.
        kfrag = KFrag.from_bytes(kfrag_bytes)
        cfrag_byte_stream = b""

        for capsule in work_order.capsules:
            # TODO: Sign the result of this.  See #141.
            cfrag_byte_stream += bytes(pre.reencrypt(kfrag, capsule))

        # TODO: Put this in Ursula's datastore
        self._work_orders.append(work_order)

        return Response(content=cfrag_byte_stream,
                        content_type="application/octet-stream")
