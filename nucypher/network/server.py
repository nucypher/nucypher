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

import binascii
import os
from typing import Callable, Tuple

from flask import Flask, Response
from flask import request
from jinja2 import Template, TemplateError
from twisted.logger import Logger
from umbral import pre
from umbral.keys import UmbralPublicKey
from umbral.kfrags import KFrag

from bytestring_splitter import VariableLengthBytestring
from constant_sorrow import constants
from constant_sorrow.constants import FLEET_STATES_MATCH
from constant_sorrow.constants import GLOBAL_DOMAIN, NO_KNOWN_NODES
from hendrix.experience import crosstown_traffic
from nucypher.config.constants import GLOBAL_DOMAIN
from nucypher.config.storages import ForgetfulNodeStorage
from nucypher.crypto.api import keccak_digest
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import SigningPower, KeyPairBasedPower, PowerUpError
from nucypher.crypto.signing import InvalidSignature
from nucypher.crypto.signing import SignatureStamp
from nucypher.keystore.keypairs import HostingKeypair
from nucypher.keystore.keystore import NotFound
from nucypher.keystore.threading import ThreadedSession
from nucypher.network import LEARNING_LOOP_VERSION
from nucypher.network.middleware import RestMiddleware
from nucypher.network.protocols import InterfaceInfo

HERE = BASE_DIR = os.path.abspath(os.path.dirname(__file__))
TEMPLATES_DIR = os.path.join(HERE, "templates")

with open(os.path.join(TEMPLATES_DIR, "basic_status.j2"), "r") as f:
    _status_template_content = f.read()
status_template = Template(_status_template_content)


class ProxyRESTServer:
    log = Logger("characters")
    SERVER_VERSION = LEARNING_LOOP_VERSION
    log = Logger("network-server")

    def __init__(self,
                 rest_host: str,
                 rest_port: int,
                 hosting_power=None,
                 rest_app=None,
                 datastore=None,
                 ) -> None:

        self.rest_interface = InterfaceInfo(host=rest_host, port=rest_port)
        if rest_app:  # if is me
            self.rest_app = rest_app
            self.datastore = datastore
        else:
            self.rest_app = constants.PUBLIC_ONLY

        self.__hosting_power = hosting_power

    def rest_url(self):
        return "{}:{}".format(self.rest_interface.host, self.rest_interface.port)


def make_rest_app(
        db_filepath: str,
        network_middleware: RestMiddleware,
        federated_only: bool,
        treasure_map_tracker: dict,
        node_tracker: 'FleetStateTracker',
        node_bytes_caster: Callable,
        work_order_tracker: list,
        node_recorder: Callable,
        stamp: SignatureStamp,
        verifier: Callable,
        suspicious_activity_tracker: dict,
        serving_domains,
        log=Logger("http-application-layer")
) -> Tuple:
    forgetful_node_storage = ForgetfulNodeStorage(federated_only=federated_only)

    from nucypher.keystore import keystore
    from nucypher.keystore.db import Base
    from sqlalchemy.engine import create_engine

    log.info("Starting datastore {}".format(db_filepath))

    # See: https://docs.sqlalchemy.org/en/rel_0_9/dialects/sqlite.html#connect-strings
    if db_filepath:
        db_uri = f'sqlite:///{db_filepath}'
    else:
        db_uri = 'sqlite://'  # TODO: Is this a sane default? See #667

    engine = create_engine(db_uri)

    Base.metadata.create_all(engine)
    datastore = keystore.KeyStore(engine)
    db_engine = engine

    from nucypher.characters.lawful import Alice, Ursula
    _alice_class = Alice
    _node_class = Ursula

    rest_app = rest_app = Flask("ursula-service")

    @rest_app.route("/public_information")
    def public_information():
        """
        REST endpoint for public keys and address..
        """
        response = Response(
            response=node_bytes_caster(),
            mimetype='application/octet-stream')

        return response

    @rest_app.route('/node_metadata', methods=["GET"])
    def all_known_nodes():
        headers = {'Content-Type': 'application/octet-stream'}

        if node_tracker.checksum is NO_KNOWN_NODES:
            return Response(b"", headers=headers, status=204)

        payload = node_tracker.snapshot()

        ursulas_as_vbytes = (VariableLengthBytestring(n) for n in node_tracker)
        ursulas_as_bytes = bytes().join(bytes(u) for u in ursulas_as_vbytes)
        ursulas_as_bytes += VariableLengthBytestring(node_bytes_caster())

        payload += ursulas_as_bytes
        signature = stamp(payload)
        return Response(bytes(signature) + payload, headers=headers)

    @rest_app.route('/node_metadata', methods=["POST"])
    def node_metadata_exchange():
        # If these nodes already have the same fleet state, no exchange is necessary.

        learner_fleet_state = request.args.get('fleet')
        if learner_fleet_state == node_tracker.checksum:
            log.debug("Learner already knew fleet state {}; doing nothing.".format(learner_fleet_state))
            headers = {'Content-Type': 'application/octet-stream'}
            payload = node_tracker.snapshot() + bytes(FLEET_STATES_MATCH)
            signature = stamp(payload)
            return Response(bytes(signature) + payload, headers=headers)

        nodes = _node_class.batch_from_bytes(request.data, federated_only=federated_only)  # TODO: 466

        # TODO: This logic is basically repeated in learn_from_teacher_node and remember_node.
        # Let's find a better way.  #555
        for node in nodes:
            if GLOBAL_DOMAIN not in serving_domains:
                if not serving_domains.intersection(node.serving_domains):
                    continue  # This node is not serving any of our domains.

            if node in node_tracker:
                if node.timestamp <= node_tracker[node.checksum_public_address].timestamp:
                    continue

            @crosstown_traffic()
            def learn_about_announced_nodes():

                try:
                    certificate_filepath = forgetful_node_storage.store_node_certificate(
                        certificate=node.certificate)

                    node.verify_node(network_middleware,
                                     accept_federated_only=federated_only,  # TODO: 466
                                     certificate_filepath=certificate_filepath)

                # Suspicion
                except node.SuspiciousActivity:
                    # TODO: Include data about caller?
                    # TODO: Account for possibility that stamp, rather than interface, was bad.
                    # TODO: Maybe also record the bytes representation separately to disk?
                    message = "Suspicious Activity: Discovered node with bad signature: {}.  Announced via REST."
                    log.warn(message)
                    suspicious_activity_tracker['vladimirs'].append(node)

                # Async Sentinel
                except Exception as e:
                    log.critical(str(e))
                    raise

                # Believable
                else:
                    log.info("Learned about previously unknown node: {}".format(node))
                    node_recorder(node)
                    # TODO: Record new fleet state

                # Cleanup
                finally:
                    forgetful_node_storage.forget()

        # TODO: What's the right status code here?  202?  Different if we already knew about the node?
        return all_known_nodes()

    @rest_app.route('/consider_arrangement', methods=['POST'])
    def consider_arrangement():
        from nucypher.policy.models import Arrangement
        arrangement = Arrangement.from_bytes(request.data)

        with ThreadedSession(db_engine) as session:
            new_policy_arrangement = datastore.add_policy_arrangement(
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

    @rest_app.route("/kFrag/<id_as_hex>", methods=['POST'])
    def set_policy(id_as_hex):
        """
        REST endpoint for setting a kFrag.
        TODO: Instead of taking a Request, use the apistar typing system to type
            a payload and validate / split it.
        TODO: Validate that the kfrag being saved is pursuant to an approved
            Policy (see #121).
        """
        policy_message_kit = UmbralMessageKit.from_bytes(request.data)

        alices_verifying_key = policy_message_kit.sender_pubkey_sig
        alice = _alice_class.from_public_keys({SigningPower: alices_verifying_key})

        try:
            cleartext = verifier(alice, policy_message_kit, decrypt=True)
        except InvalidSignature:
            # TODO: Perhaps we log this?
            return Response(status_code=400)

        kfrag = KFrag.from_bytes(cleartext)

        if not kfrag.verify(signing_pubkey=alices_verifying_key):
            raise InvalidSignature("{} is invalid".format(kfrag))

        with ThreadedSession(db_engine) as session:
            datastore.attach_kfrag_to_saved_arrangement(
                alice,
                id_as_hex,
                kfrag,
                session=session)

        # TODO: Sign the arrangement here.  #495
        return ""  # TODO: Return A 200, with whatever policy metadata.

    @rest_app.route('/kFrag/<id_as_hex>', methods=["DELETE"])
    def revoke_arrangement(id_as_hex):
        """
        REST endpoint for revoking/deleting a KFrag from a node.
        """
        from nucypher.policy.models import Revocation

        revocation = Revocation.from_bytes(request.data)
        # TODO: This line sometimes raises an error because it tries to log the bytes of the revocation, which can have a "{"  # 724
        log.info("Received revocation: {} -- for arrangement {}".format(bytes(revocation), id_as_hex))
        try:
            with ThreadedSession(db_engine) as session:
                # Verify the Notice was signed by Alice
                policy_arrangement = datastore.get_policy_arrangement(
                    id_as_hex.encode(), session=session)
                alice_pubkey = UmbralPublicKey.from_bytes(
                    policy_arrangement.alice_pubkey_sig.key_data)

                # Check that the request is the same for the provided revocation
                if id_as_hex != revocation.arrangement_id.hex():
                    log.debug("Couldn't identify an arrangement with id {}".format(id_as_hex))
                    return Response(status_code=400)
                elif revocation.verify_signature(alice_pubkey):
                    datastore.del_policy_arrangement(
                        id_as_hex.encode(), session=session)
        except (NotFound, InvalidSignature) as e:
            log.debug("Exception attempting to revoke: {}".format(e))
            return Response(response='KFrag not found or revocation signature is invalid.', status=404)
        else:
            log.info("KFrag successfully removed.")
            return Response(response='KFrag deleted!', status=200)

    @rest_app.route('/kFrag/<id_as_hex>/reencrypt', methods=["POST"])
    def reencrypt_via_rest(id_as_hex):
        from nucypher.policy.models import WorkOrder  # Avoid circular import
        arrangement_id = binascii.unhexlify(id_as_hex)
        work_order = WorkOrder.from_rest_payload(arrangement_id, request.data)
        log.info("Work Order from {}, signed {}".format(work_order.bob, work_order.receipt_signature))
        with ThreadedSession(db_engine) as session:
            policy_arrangement = datastore.get_policy_arrangement(arrangement_id=id_as_hex.encode(),
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
            capsule_signed_by_both = bytes(stamp(capsule_signature))

            capsule.set_correctness_keys(verifying=alices_verifying_key)
            cfrag = pre.reencrypt(kfrag, capsule, metadata=capsule_signed_by_both)
            log.info("Re-encrypting for {}, made {}.".format(capsule, cfrag))
            signature = stamp(bytes(cfrag) + bytes(capsule))
            cfrag_byte_stream += VariableLengthBytestring(cfrag) + signature

        # TODO: Put this in Ursula's datastore
        work_order_tracker.append(work_order)

        headers = {'Content-Type': 'application/octet-stream'}

        return Response(response=cfrag_byte_stream, headers=headers)

    @rest_app.route('/treasure_map/<treasure_map_id>')
    def provide_treasure_map(treasure_map_id):
        headers = {'Content-Type': 'application/octet-stream'}

        try:
            treasure_map = treasure_map_tracker[keccak_digest(binascii.unhexlify(treasure_map_id))]
            response = Response(bytes(treasure_map), headers=headers)
            log.info("{} providing TreasureMap {}".format(node_bytes_caster(),
                                                          treasure_map_id))
        except KeyError:
            log.info("{} doesn't have requested TreasureMap {}".format(stamp, treasure_map_id))
            response = Response("No Treasure Map with ID {}".format(treasure_map_id),
                                status=404, headers=headers)

        return response

    @rest_app.route('/treasure_map/<treasure_map_id>', methods=['POST'])
    def receive_treasure_map(treasure_map_id):
        from nucypher.policy.models import TreasureMap

        try:
            treasure_map = TreasureMap.from_bytes(
                bytes_representation=request.data,
                verify=True)
        except TreasureMap.InvalidSignature:
            do_store = False
        else:
            do_store = treasure_map.public_id() == treasure_map_id

        if do_store:
            log.info("{} storing TreasureMap {}".format(stamp, treasure_map_id))

            # # # #
            # TODO: Now that the DHT is retired, let's do this another way.
            # self.dht_server.set_now(binascii.unhexlify(treasure_map_id),
            #                         constants.BYTESTRING_IS_TREASURE_MAP + bytes(treasure_map))
            # # # #

            # TODO 341 - what if we already have this TreasureMap?
            treasure_map_tracker[keccak_digest(binascii.unhexlify(treasure_map_id))] = treasure_map
            return Response(bytes(treasure_map), status=202)
        else:
            # TODO: Make this a proper 500 or whatever.
            log.info("Bad TreasureMap ID; not storing {}".format(treasure_map_id))
            assert False

    @rest_app.route('/status')
    def status():
        # TODO: Seems very strange to deserialize *this node* when we can just pass it in.
        #       Might be a sign that we need to rethnk this composition.

        headers = {"Content-Type": "text/html", "charset": "utf-8"}
        this_node = _node_class.from_bytes(node_bytes_caster(), federated_only=federated_only)

        previous_states = list(reversed(node_tracker.states.values()))[:5]

        try:
            content = status_template.render(this_node=this_node,
                                             known_nodes=node_tracker,
                                             previous_states=previous_states)
        except Exception as e:
            log.debug("Template Rendering Exception: ".format(str(e)))
            raise TemplateError(str(e)) from e

        return Response(response=content, headers=headers)

    return rest_app, datastore


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
