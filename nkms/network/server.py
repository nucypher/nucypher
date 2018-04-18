import asyncio
import binascii
import random
from typing import ClassVar

from apistar import http, Route, App
from apistar.http import Response
from kademlia.crawling import NodeSpiderCrawl
from kademlia.network import Server
from kademlia.utils import digest
from umbral import pre
from umbral.fragments import KFrag

from nkms.crypto.kits import UmbralMessageKit
from nkms.crypto.powers import EncryptingPower, SigningPower
from nkms.keystore.threading import ThreadedSession
from nkms.network.capabilities import SeedOnly, ServerCapability
from nkms.network.node import NuCypherNode
from nkms.network.protocols import NuCypherSeedOnlyProtocol, NuCypherHashProtocol, \
    dht_value_splitter, dht_with_hrac_splitter
from nkms.network.storage import SeedOnlyStorage


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

    def __init__(self, rest_port, db_name):
        self.rest_port = rest_port
        self.db_name = db_name
        self._rest_app = None

    def public_key(self, power_class: ClassVar):
        """Implemented on Ursula subclass"""
        raise NotImplementedError

    def attach_rest_server(self, db_name):

        routes = [
            Route('/kFrag/{hrac_as_hex}',
                  'POST',
                  self.set_policy),
            Route('/kFrag/{hrac_as_hex}/reencrypt',
                  'POST',
                  self.reencrypt_via_rest),
            Route('/public_keys', 'GET',
                  self.get_signing_and_encrypting_public_keys),
            Route('/list_nodes', 'GET',
                  self.list_all_active_nodes_about_which_we_know),
            Route('/consider_arrangement',
                  'POST',
                  self.consider_arrangement),
            Route('/treasure_map/{treasure_map_id_as_hex}',
                  'GET',
                  self.provide_treasure_map),
            Route('/treasure_map/{treasure_map_id_as_hex}',
                  'POST',
                  self.receive_treasure_map),
        ]

        self._rest_app = App(routes=routes)
        self.start_datastore(db_name)

    def start_datastore(self, db_name):
        if not db_name:
            raise TypeError("In order to start a datastore, you need to supply a db_name.")

        from nkms.keystore import keystore
        from nkms.keystore.db import Base
        from sqlalchemy.engine import create_engine

        engine = create_engine('sqlite:///{}'.format(db_name))
        Base.metadata.create_all(engine)
        self.datastore = keystore.KeyStore(engine)
        self.db_engine = engine

    def rest_url(self):
        return "{}:{}".format(self.ip_address, self.rest_port)


    #####################################
    # Actual REST Endpoints and utilities
    #####################################

    def get_signing_and_encrypting_public_keys(self):
        """
        REST endpoint for getting both signing and encrypting public keys.
        """

        headers = {'Content-Type': 'application/octet-stream'}
        response = Response(
            content=bytes(self.public_key(SigningPower)) + bytes(self.public_key(EncryptingPower)),
            headers=headers)

        return response

    def list_all_active_nodes_about_which_we_know(self):
        headers = {'Content-Type': 'application/octet-stream'}
        ursulas_as_bytes = bytes().join(self.server.protocol.ursulas.values())
        ursulas_as_bytes += self.interface_info_with_metadata()
        signature = self.stamp(ursulas_as_bytes)
        return Response(bytes(signature) + ursulas_as_bytes, headers=headers)

    def consider_arrangement(self, request: http.Request):
        from nkms.policy.models import Arrangement
        arrangement = Arrangement.from_bytes(request.body)

        with ThreadedSession(self.db_engine) as session:
            new_policyarrangement = self.datastore.add_policy_arrangement(
                arrangement.expiration.datetime(),
                bytes(arrangement.deposit),
                hrac=arrangement.hrac.hex().encode(),
                alice_pubkey_sig=arrangement.alice.stamp,
                session=session,
            )
        # TODO: Make the rest of this logic actually work - do something here
        # to decide if this Arrangement is worth accepting.

        headers = {'Content-Type': 'application/octet-stream'}
        # TODO: Make this a legit response #234.
        return Response(b"This will eventually be an actual acceptance of the arrangement.", headers=headers)

    def set_policy(self, hrac_as_hex, request: http.Request):
        """
        REST endpoint for setting a kFrag.
        TODO: Instead of taking a Request, use the apistar typing system to type
            a payload and validate / split it.
        TODO: Validate that the kfrag being saved is pursuant to an approved
            Policy (see #121).
        """
        hrac = binascii.unhexlify(hrac_as_hex)
        policy_message_kit = UmbralMessageKit.from_bytes(request.body)
        # group_payload_splitter = BytestringSplitter(PublicKey)
        # policy_payload_splitter = BytestringSplitter((KFrag, KFRAG_LENGTH))

        alice = self._alice_class.from_public_keys({SigningPower: policy_message_kit.sender_pubkey_sig})

        verified, cleartext = self.verify_from(alice, policy_message_kit, decrypt=True)

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

        with ThreadedSession(self.db_engine) as session:
            self.datastore.attach_kfrag_to_saved_arrangement(
                                               alice,
                                               hrac_as_hex,
                                               kfrag,
                                               session=session)

        return  # TODO: Return A 200, with whatever policy metadata.

    def reencrypt_via_rest(self, hrac_as_hex, request: http.Request):
        from nkms.policy.models import WorkOrder  # Avoid circular import
        hrac = binascii.unhexlify(hrac_as_hex)
        work_order = WorkOrder.from_rest_payload(hrac, request.body)
        with ThreadedSession(self.db_engine) as session:
            kfrag_bytes = self.datastore.get_policy_arrangement(hrac.hex().encode(),
                                                             session=session).k_frag  # Careful!  :-)
        # TODO: Push this to a lower level.
        kfrag = KFrag.from_bytes(kfrag_bytes)
        cfrag_byte_stream = b""

        for capsule in work_order.capsules:
            # TODO: Sign the result of this.  See #141.
            cfrag_byte_stream += bytes(pre.reencrypt(kfrag, capsule))

        # TODO: Put this in Ursula's datastore
        self._work_orders.append(work_order)

        headers = {'Content-Type': 'application/octet-stream'}

        return Response(content=cfrag_byte_stream, headers=headers)

    def provide_treasure_map(self, treasure_map_id_as_hex):
        # For now, grab the TreasureMap for the DHT storage.  Soon, no do that.  #TODO!
        treasure_map_id = binascii.unhexlify(treasure_map_id_as_hex)
        headers = {'Content-Type': 'application/octet-stream'}

        try:
            treasure_map_bytes = self.server.storage[digest(treasure_map_id)]
            response = Response(content=treasure_map_bytes, headers=headers)
        except KeyError:
            response = Response("No Treasure Map with ID {}".format(treasure_map_id),
                                status_code=404, headers=headers)

        return response

    def receive_treasure_map(self, treasure_map_id_as_hex, request: http.Request):
        # TODO: This function is the epitome of #172.
        treasure_map_id = binascii.unhexlify(treasure_map_id_as_hex)

        header, signature_for_ursula, pubkey_sig_alice, hrac, tmap_message_kit = \
            dht_with_hrac_splitter(request.body, return_remainder=True)
        # TODO: This next line is possibly the worst in the entire codebase at the moment.  #172.
        # Also TODO: TTL?
        do_store = self.server.protocol.determine_legality_of_dht_key(
                    signature_for_ursula, pubkey_sig_alice, tmap_message_kit,
                    hrac, digest(treasure_map_id), request.body)
        if do_store:
            # TODO: Stop storing things in the protocol storage.  Do this better.  #227
            # TODO: Propagate to other nodes.  #235
            self.server.protocol.storage[digest(treasure_map_id)] = request.body
            return # TODO: Proper response here.
        else:
            # TODO: Make this a proper 500 or whatever.
            assert False

