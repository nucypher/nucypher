import binascii
import os
from logging import getLogger

from apistar import Route, App
from apistar.http import Response, Request, QueryParams
from bytestring_splitter import VariableLengthBytestring
from constant_sorrow import constants
from hendrix.experience import crosstown_traffic
from umbral import pre
from umbral.fragments import KFrag
from umbral.keys import UmbralPublicKey

from nucypher.crypto.api import keccak_digest
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import SigningPower, KeyPairBasedPower, PowerUpError
from nucypher.keystore.keypairs import HostingKeypair
from nucypher.keystore.threading import ThreadedSession
from nucypher.network.protocols import InterfaceInfo


class ProxyRESTServer:
    log = getLogger("characters")

    def __init__(self,
                 rest_host: str,
                 rest_port: int,
                 hosting_power = None,
                 routes: 'ProxyRESTRoutes' = None,
                 ) -> None:

        self.routes = routes
        self.rest_interface = InterfaceInfo(host=rest_host, port=rest_port)
        if routes:  # if is me
            self.rest_app = routes.rest_app
            self.db_filepath = routes.db_filepath
        else:
            self.rest_app = constants.PUBLIC_ONLY

        self.__hosting_power = hosting_power

    def rest_url(self):
        return "{}:{}".format(self.rest_interface.host, self.rest_interface.port)


class ProxyRESTRoutes:
    log = getLogger("characters")

    class InvalidSignature(Exception):
        """Raised when a received signature is not valid."""

    def __init__(self,
                 db_name,
                 db_filepath,
                 network_middleware,
                 federated_only,
                 treasure_map_tracker,
                 node_tracker,
                 node_bytes_caster,
                 work_order_tracker,
                 node_recorder,
                 stamp,
                 verifier,
                 suspicious_activity_tracker,
                 certificate_dir,
                 ) -> None:

        self.network_middleware = network_middleware
        self.federated_only = federated_only

        self._treasure_map_tracker = treasure_map_tracker
        self._work_order_tracker = work_order_tracker
        self._node_tracker = node_tracker
        self._node_bytes_caster = node_bytes_caster
        self._node_recorder = node_recorder
        self._stamp = stamp
        self._verifier = verifier
        self._suspicious_activity_tracker = suspicious_activity_tracker
        self._certificate_dir = certificate_dir
        self.datastore = None

        routes = [
            Route('/kFrag/{id_as_hex}',
                  'POST',
                  self.set_policy),
            Route('/kFrag/{id_as_hex}/reencrypt',
                  'POST',
                  self.reencrypt_via_rest),
            Route('/public_information', 'GET',
                  self.public_information),
            Route('/node_metadata', 'GET',
                  self.all_known_nodes),
            Route('/node_metadata', 'POST',
                  self.node_metadata_exchange),
            Route('/consider_arrangement',
                  'POST',
                  self.consider_arrangement),
            Route('/treasure_map/{treasure_map_id}',
                  'GET',
                  self.provide_treasure_map),
            Route('/treasure_map/{treasure_map_id}',
                  'POST',
                  self.receive_treasure_map),
        ]

        self.rest_app = App(routes=routes)
        self.db_name = db_name
        self.db_filepath = db_filepath

        from nucypher.keystore import keystore
        from nucypher.keystore.db import Base
        from sqlalchemy.engine import create_engine

        self.log.info("Starting datastore {}".format(self.db_filepath))
        engine = create_engine('sqlite:///{}'.format(self.db_filepath))
        Base.metadata.create_all(engine)
        self.datastore = keystore.KeyStore(engine)
        self.db_engine = engine

        from nucypher.characters.lawful import Alice, Ursula
        self._alice_class = Alice
        self._node_class = Ursula

    def public_information(self):
        """
        REST endpoint for public keys and address..
        """
        headers = {'Content-Type': 'application/octet-stream'}
        response = Response(
            content=self._node_bytes_caster(),
            headers=headers)

        return response

    def all_known_nodes(self, request: Request):
        headers = {'Content-Type': 'application/octet-stream'}
        ursulas_as_bytes = bytes().join(bytes(n) for n in self._node_tracker.values())
        ursulas_as_bytes += self._node_bytes_caster()
        signature = self._stamp(ursulas_as_bytes)
        return Response(bytes(signature) + ursulas_as_bytes, headers=headers)

    def node_metadata_exchange(self, request: Request, query_params: QueryParams):
        nodes = self._node_class.batch_from_bytes(request.body,
                                                  federated_only=self.federated_only,  # TODO: 466
                                                  )
        # TODO: This logic is basically repeated in learn_from_teacher_node.  Let's find a better way.
        for node in nodes:

            if node.checksum_public_address in self._node_tracker:
                continue  # TODO: 168 Check version and update if required.

            @crosstown_traffic()
            def learn_about_announced_nodes():
                try:
                    certificate_filepath = node.get_certificate_filepath(certificates_dir=self._certificate_dir)  # TODO: integrate with recorder?
                    node.save_certificate_to_disk(directory=self._certificate_dir, force=True)
                    node.verify_node(self.network_middleware,
                                     accept_federated_only=self.federated_only,  # TODO: 466
                                     certificate_filepath=certificate_filepath)
                except node.SuspiciousActivity:
                    # TODO: Account for possibility that stamp, rather than interface, was bad.
                    message = "Suspicious Activity: Discovered node with bad signature: {}.  " \
                              " Announced via REST."  # TODO: Include data about caller?
                    self.log.warning(message)
                    self._suspicious_activity_tracker['vladimirs'].append(node)  # TODO: Maybe also record the bytes representation separately to disk?
                except Exception as e:
                    self.log.critical(str(e))
                    raise  # TODO
                else:
                    self.log.info("Previously unknown node: {}".format(node.checksum_public_address))
                    self._node_recorder(node)

        # TODO: What's the right status code here?  202?  Different if we already knew about the node?
        return self.all_known_nodes(request)

    def consider_arrangement(self, request: Request):
        from nucypher.policy.models import Arrangement
        arrangement = Arrangement.from_bytes(request.body)

        with ThreadedSession(self.db_engine) as session:
            new_policyarrangement = self.datastore.add_policy_arrangement(
                arrangement.expiration.datetime(),
                id=arrangement.id.hex().encode(),
                alice_pubkey_sig=arrangement.alice.stamp,
                session=session,
            )
        # TODO: Make the rest of this logic actually work - do something here
        # to decide if this Arrangement is worth accepting.

        headers = {'Content-Type': 'application/octet-stream'}
        # TODO: Make this a legit response #234.
        return Response(b"This will eventually be an actual acceptance of the arrangement.", headers=headers)

    def set_policy(self, id_as_hex, request: Request):
        """
        REST endpoint for setting a kFrag.
        TODO: Instead of taking a Request, use the apistar typing system to type
            a payload and validate / split it.
        TODO: Validate that the kfrag being saved is pursuant to an approved
            Policy (see #121).
        """
        policy_message_kit = UmbralMessageKit.from_bytes(request.body)

        alices_verifying_key = policy_message_kit.sender_pubkey_sig
        alice = self._alice_class.from_public_keys({SigningPower: alices_verifying_key})

        try:
            cleartext = self._verifier(alice, policy_message_kit, decrypt=True)
        except self.InvalidSignature:
            # TODO: Perhaps we log this?
            return Response(status_code=400)

        kfrag = KFrag.from_bytes(cleartext)

        if not kfrag.verify(signing_pubkey=alices_verifying_key):
            raise self.InvalidSignature("{} is invalid".format(kfrag))

        with ThreadedSession(self.db_engine) as session:
            self.datastore.attach_kfrag_to_saved_arrangement(
                alice,
                id_as_hex,
                kfrag,
                session=session)

        return  # TODO: Return A 200, with whatever policy metadata.

    def reencrypt_via_rest(self, id_as_hex, request: Request):
        from nucypher.policy.models import WorkOrder  # Avoid circular import
        arrangement_id = binascii.unhexlify(id_as_hex)
        work_order = WorkOrder.from_rest_payload(arrangement_id, request.body)
        self.log.info("Work Order from {}, signed {}".format(work_order.bob, work_order.receipt_signature))
        with ThreadedSession(self.db_engine) as session:
            policy_arrangement = self.datastore.get_policy_arrangement(arrangement_id=id_as_hex.encode(),
                                                                       session=session)

        kfrag_bytes = policy_arrangement.kfrag  # Careful!  :-)
        verifying_key_bytes = policy_arrangement.alice_pubkey_sig.key_data

        # TODO: Push this to a lower level.
        kfrag = KFrag.from_bytes(kfrag_bytes)
        alices_verifying_key = UmbralPublicKey.from_bytes(verifying_key_bytes)
        cfrag_byte_stream = b""

        for capsule, capsule_signature in zip(work_order.capsules, work_order.capsule_signatures):
            # This is the capsule signed by Bob
            capsule_signature = bytes(capsule_signature)
            # Ursula signs on top of it. Now both are committed to the same capsule.
            capsule_signed_by_both = bytes(self._stamp(capsule_signature))

            capsule.set_correctness_keys(verifying=alices_verifying_key)
            cfrag = pre.reencrypt(kfrag, capsule, metadata=capsule_signed_by_both)
            self.log.info("Re-encrypting for {}, made {}.".format(capsule, cfrag))
            signature = self._stamp(bytes(cfrag))
            cfrag_byte_stream += VariableLengthBytestring(cfrag) + signature

        # TODO: Put this in Ursula's datastore
        self._work_order_tracker.append(work_order)

        headers = {'Content-Type': 'application/octet-stream'}

        return Response(content=cfrag_byte_stream, headers=headers)

    def provide_treasure_map(self, treasure_map_id):
        headers = {'Content-Type': 'application/octet-stream'}

        try:
            treasure_map = self._treasure_map_tracker[keccak_digest(binascii.unhexlify(treasure_map_id))]
            response = Response(content=bytes(treasure_map), headers=headers)
            self.log.info("{} providing TreasureMap {}".format(self._node_bytes_caster(),
                                                               treasure_map_id))
        except KeyError:
            self.log.info("{} doesn't have requested TreasureMap {}".format(self, treasure_map_id))
            response = Response("No Treasure Map with ID {}".format(treasure_map_id),
                                status_code=404, headers=headers)

        return response

    def receive_treasure_map(self, treasure_map_id, request: Request):
        from nucypher.policy.models import TreasureMap

        try:
            treasure_map = TreasureMap.from_bytes(
                bytes_representation=request.body,
                verify=True)
        except TreasureMap.InvalidSignature:
            do_store = False
        else:
            do_store = treasure_map.public_id() == treasure_map_id

        if do_store:
            self.log.info("{} storing TreasureMap {}".format(self, treasure_map_id))

            # # # #
            # TODO: Now that the DHT is retired, let's do this another way.
            # self.dht_server.set_now(binascii.unhexlify(treasure_map_id),
            #                         constants.BYTESTRING_IS_TREASURE_MAP + bytes(treasure_map))
            # # # #

            # TODO 341 - what if we already have this TreasureMap?
            self._treasure_map_tracker[keccak_digest(binascii.unhexlify(treasure_map_id))] = treasure_map
            return Response(content=bytes(treasure_map), status_code=202)
        else:
            # TODO: Make this a proper 500 or whatever.
            self.log.info("Bad TreasureMap ID; not storing {}".format(treasure_map_id))
            assert False


class TLSHostingPower(KeyPairBasedPower):
    _keypair_class = HostingKeypair
    provides = ("get_deployer",)

    class NoHostingPower(PowerUpError):
        pass

    not_found_error = NoHostingPower

    def __init__(self,
                 host: str,
                 public_certificate=None,
                 public_certificate_filepath=None,
                 *args, **kwargs) -> None:

        if public_certificate and public_certificate_filepath:
            # TODO: Design decision here: if they do pass both, and they're identical, do we let that slide?
            raise ValueError("Pass either a public_certificate or a public_certificate_filepath, not both.")

        if public_certificate:
            kwargs['keypair'] = HostingKeypair(certificate=public_certificate, host=host)
        elif public_certificate_filepath:
            kwargs['keypair'] = HostingKeypair(certificate_filepath=public_certificate_filepath, host=host)
        super().__init__(*args, **kwargs)
