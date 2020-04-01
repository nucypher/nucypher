"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import binascii
import json
import os
from typing import Tuple

import requests
from bytestring_splitter import BytestringSplitter
from constant_sorrow import constants
from constant_sorrow.constants import FLEET_STATES_MATCH, NO_KNOWN_NODES
from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION
from flask import Flask, Response, request
from flask import jsonify
from hendrix.experience import crosstown_traffic
from jinja2 import Template, TemplateError
from twisted.logger import Logger
from umbral.keys import UmbralPublicKey
from umbral.kfrags import KFrag
from web3.exceptions import TimeExhausted

import nucypher
from nucypher.config.storages import ForgetfulNodeStorage
from nucypher.config.constants import MAX_UPLOAD_CONTENT_LENGTH
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import KeyPairBasedPower, PowerUpError
from nucypher.crypto.signing import InvalidSignature
from nucypher.crypto.utils import canonical_address_from_umbral_key
from nucypher.datastore.keypairs import HostingKeypair
from nucypher.datastore.datastore import NotFound
from nucypher.datastore.threading import ThreadedSession
from nucypher.network import LEARNING_LOOP_VERSION
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.protocols import InterfaceInfo

HERE = BASE_DIR = os.path.abspath(os.path.dirname(__file__))
TEMPLATES_DIR = os.path.join(HERE, "templates")

with open(os.path.join(TEMPLATES_DIR, "basic_status.j2"), "r") as f:
    _status_template_content = f.read()
status_template = Template(_status_template_content)


class ProxyRESTServer:
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
        this_node,
        serving_domains,
        log=Logger("http-application-layer")
        ) -> Tuple:

    forgetful_node_storage = ForgetfulNodeStorage(federated_only=this_node.federated_only)

    from nucypher.datastore import datastore
    from nucypher.datastore.db import Base
    from sqlalchemy.engine import create_engine

    log.info("Starting datastore {}".format(db_filepath))

    # See: https://docs.sqlalchemy.org/en/rel_0_9/dialects/sqlite.html#connect-strings
    if db_filepath:
        db_uri = f'sqlite:///{db_filepath}'
    else:
        db_uri = 'sqlite://'  # TODO: Is this a sane default? See #667

    engine = create_engine(db_uri)

    Base.metadata.create_all(engine)
    datastore = datastore.Datastore(engine)
    db_engine = engine

    from nucypher.characters.lawful import Alice, Ursula
    _alice_class = Alice
    _node_class = Ursula

    rest_app = Flask("ursula-service")
    rest_app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_CONTENT_LENGTH

    @rest_app.route("/public_information")
    def public_information():
        """
        REST endpoint for public keys and address.
        """
        response = Response(
            response=bytes(this_node),
            mimetype='application/octet-stream')

        return response

    @rest_app.route("/ping", methods=['POST'])
    def ping():
        """
        Asks this node: "Can you access my public information endpoint"?
        """

        try:
            requesting_ursula = Ursula.from_bytes(request.data, registry=this_node.registry)
            requesting_ursula.mature()
        except ValueError:  # (ValueError)
            return Response({'error': 'Invalid Ursula'}, status=400)
        else:
            initiator_address, initiator_port = tuple(requesting_ursula.rest_interface)

        # Compare requester and posted Ursula information
        request_address = request.environ['REMOTE_ADDR']
        if request_address != initiator_address:
            return Response({'error': 'Suspicious origin address'}, status=400)

        #
        # Make a Sandwich
        #

        try:
            # Fetch and store initiator's teacher certificate.
            certificate = this_node.network_middleware.get_certificate(host=initiator_address, port=initiator_port)
            certificate_filepath = this_node.node_storage.store_node_certificate(certificate=certificate)
            requesting_ursula_bytes = this_node.network_middleware.client.node_information(host=initiator_address,
                                                                                           port=initiator_port,
                                                                                           certificate_filepath=certificate_filepath)
        except NodeSeemsToBeDown:
            return Response({'error': 'Unreachable node'}, status=400)  # ... toasted

        # Compare the results of the outer POST with the inner GET... yum
        if requesting_ursula_bytes == request.data:
            return Response(status=200)
        else:
            return Response({'error': 'Suspicious node'}, status=400)

    @rest_app.route('/node_metadata', methods=["GET"])
    def all_known_nodes():
        headers = {'Content-Type': 'application/octet-stream'}

        if this_node.known_nodes.checksum is NO_KNOWN_NODES:
            return Response(b"", headers=headers, status=204)

        known_nodes_bytestring = this_node.bytestring_of_known_nodes()
        signature = this_node.stamp(known_nodes_bytestring)
        return Response(bytes(signature) + known_nodes_bytestring, headers=headers)

    @rest_app.route('/node_metadata', methods=["POST"])
    def node_metadata_exchange():
        # If these nodes already have the same fleet state, no exchange is necessary.

        learner_fleet_state = request.args.get('fleet')
        if learner_fleet_state == this_node.known_nodes.checksum:
            log.debug("Learner already knew fleet state {}; doing nothing.".format(learner_fleet_state))
            headers = {'Content-Type': 'application/octet-stream'}
            payload = this_node.known_nodes.snapshot() + bytes(FLEET_STATES_MATCH)
            signature = this_node.stamp(payload)
            return Response(bytes(signature) + payload, headers=headers)

        sprouts = _node_class.batch_from_bytes(request.data,
                                             registry=this_node.registry)

        # TODO: This logic is basically repeated in learn_from_teacher_node and remember_node.
        # Let's find a better way.  #555
        for node in sprouts:
            @crosstown_traffic()
            def learn_about_announced_nodes():
                if node in this_node.known_nodes:
                    if node.timestamp <= this_node.known_nodes[node.checksum_address].timestamp:
                        return

                node.mature()

                try:
                    node.verify_node(this_node.network_middleware.client,
                                     registry=this_node.registry)

                # Suspicion
                except node.SuspiciousActivity as e:
                    # 355
                    # TODO: Include data about caller?
                    # TODO: Account for possibility that stamp, rather than interface, was bad.
                    # TODO: Maybe also record the bytes representation separately to disk?
                    message = f"Suspicious Activity about {node}: {str(e)}.  Announced via REST."
                    log.warn(message)
                    this_node.suspicious_activities_witnessed['vladimirs'].append(node)
                except NodeSeemsToBeDown as e:
                    # This is a rather odd situation - this node *just* contacted us and asked to be verified.  Where'd it go?  Maybe a NAT problem?
                    log.info(f"Node announced itself to us just now, but seems to be down: {node}.  Response was {e}.")
                    log.debug(f"Phantom node certificate: {node.certificate}")
                # Async Sentinel
                except Exception as e:
                    log.critical(f"This exception really needs to be handled differently: {e}")
                    raise

                # Believable
                else:
                    log.info("Learned about previously unknown node: {}".format(node))
                    this_node.remember_node(node)
                    # TODO: Record new fleet state

                # Cleanup
                finally:
                    forgetful_node_storage.forget()

        # TODO: What's the right status code here?  202?  Different if we already knew about the node?
        return all_known_nodes()

    @rest_app.route('/consider_arrangement', methods=['POST'])
    def consider_arrangement():
        from nucypher.policy.policies import Arrangement
        arrangement = Arrangement.from_bytes(request.data)

        # TODO: Look at the expiration and figure out if we're even staking that long.  1701
        with ThreadedSession(db_engine) as session:
            new_policy_arrangement = datastore.add_policy_arrangement(
                arrangement.expiration.datetime(),
                arrangement_id=arrangement.id.hex().encode(),
                alice_verifying_key=arrangement.alice.stamp,
                session=session,
            )
        # TODO: Fine, we'll add the arrangement here, but if we never hear from Alice again to enact it,
        # we need to prune it at some point.  #1700

        headers = {'Content-Type': 'application/octet-stream'}
        # TODO: Make this a legit response #234.
        return Response(b"This will eventually be an actual acceptance of the arrangement.", headers=headers)

    @rest_app.route("/kFrag/<id_as_hex>", methods=['POST'])
    def set_policy(id_as_hex):
        """
        REST endpoint for setting a kFrag.
        """
        policy_message_kit = UmbralMessageKit.from_bytes(request.data)

        alices_verifying_key = policy_message_kit.sender_verifying_key
        alice = _alice_class.from_public_keys(verifying_key=alices_verifying_key)

        try:
            cleartext = this_node.verify_from(alice, policy_message_kit, decrypt=True)
        except InvalidSignature:
            # TODO: Perhaps we log this?  Essentially 355.
            return Response(status_code=400)

        if not this_node.federated_only:
            # This splitter probably belongs somewhere canonical.
            transaction_splitter = BytestringSplitter(32)
            tx, kfrag_bytes = transaction_splitter(cleartext, return_remainder=True)

            try:
                # Get all of the arrangements and verify that we'll be paid.
                # TODO: We'd love for this part to be impossible to reduce the risk of collusion.  #1274
                arranged_addresses = this_node.policy_agent.fetch_arrangement_addresses_from_policy_txid(tx, timeout=this_node.synchronous_query_timeout)
            except TimeExhausted:
                # Alice didn't pay.  Return response with that weird status code.
                this_node.suspicious_activities_witnessed['freeriders'].append((alice, f"No transaction matching {tx}."))
                return Response(status=402)

            this_node_has_been_arranged = this_node.checksum_address in arranged_addresses
            if not this_node_has_been_arranged:
                this_node.suspicious_activities_witnessed['freeriders'].append((alice, f"The transaction {tx} does not list me as a Worker - it lists {arranged_addresses}."))
                return Response(status=402)
        else:
            _tx = NO_BLOCKCHAIN_CONNECTION
            kfrag_bytes = cleartext
        kfrag = KFrag.from_bytes(kfrag_bytes)

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
        from nucypher.policy.collections import Revocation

        revocation = Revocation.from_bytes(request.data)
        log.info("Received revocation: {} -- for arrangement {}".format(bytes(revocation).hex(), id_as_hex))
        try:
            with ThreadedSession(db_engine) as session:
                # Verify the Notice was signed by Alice
                policy_arrangement = datastore.get_policy_arrangement(
                    id_as_hex.encode(), session=session)
                alice_pubkey = UmbralPublicKey.from_bytes(
                    policy_arrangement.alice_verifying_key.key_data)

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

        # Get Policy Arrangement
        try:
            arrangement_id = binascii.unhexlify(id_as_hex)
        except (binascii.Error, TypeError):
            return Response(response=b'Invalid arrangement ID', status=405)
        try:
            with ThreadedSession(db_engine) as session:
                arrangement = datastore.get_policy_arrangement(arrangement_id=id_as_hex.encode(), session=session)
        except NotFound:
            return Response(response=arrangement_id, status=404)

        # Get KFrag
        # TODO: Yeah, well, what if this arrangement hasn't been enacted?  1702
        kfrag = KFrag.from_bytes(arrangement.kfrag)

        # Get Work Order
        from nucypher.policy.collections import WorkOrder  # Avoid circular import
        alice_verifying_key_bytes = arrangement.alice_verifying_key.key_data
        alice_verifying_key = UmbralPublicKey.from_bytes(alice_verifying_key_bytes)
        alice_address = canonical_address_from_umbral_key(alice_verifying_key)
        work_order_payload = request.data
        work_order = WorkOrder.from_rest_payload(arrangement_id=arrangement_id,
                                                 rest_payload=work_order_payload,
                                                 ursula=this_node,
                                                 alice_address=alice_address)
        log.info(f"Work Order from {work_order.bob}, signed {work_order.receipt_signature}")

        # Re-encrypt
        response = this_node._reencrypt(kfrag=kfrag,
                                        work_order=work_order,
                                        alice_verifying_key=alice_verifying_key)

        # Now, Ursula saves this workorder to her database...
        with ThreadedSession(db_engine):
            this_node.datastore.save_workorder(bob_verifying_key=bytes(work_order.bob.stamp),
                                               bob_signature=bytes(work_order.receipt_signature),
                                               arrangement_id=work_order.arrangement_id)

        headers = {'Content-Type': 'application/octet-stream'}
        return Response(headers=headers, response=response)

    @rest_app.route('/treasure_map/<treasure_map_id>')
    def provide_treasure_map(treasure_map_id):
        headers = {'Content-Type': 'application/octet-stream'}

        treasure_map_index = bytes.fromhex(treasure_map_id)

        try:

            treasure_map = this_node.treasure_maps[treasure_map_index]
            response = Response(bytes(treasure_map), headers=headers)
            log.info("{} providing TreasureMap {}".format(this_node.nickname, treasure_map_id))

        except KeyError:
            log.info("{} doesn't have requested TreasureMap {}".format(this_node.stamp, treasure_map_id))
            response = Response("No Treasure Map with ID {}".format(treasure_map_id),
                                status=404, headers=headers)

        return response

    @rest_app.route('/treasure_map/<treasure_map_id>', methods=['POST'])
    def receive_treasure_map(treasure_map_id):
        from nucypher.policy.collections import TreasureMap

        try:
            treasure_map = TreasureMap.from_bytes(bytes_representation=request.data, verify=True)
        except TreasureMap.InvalidSignature:
            do_store = False
        else:
            # TODO: If we include the policy ID in this check, does that prevent map spam?  1736
            do_store = treasure_map.public_id() == treasure_map_id

        if do_store:
            log.info("{} storing TreasureMap {}".format(this_node, treasure_map_id))

            # TODO 341 - what if we already have this TreasureMap?
            treasure_map_index = bytes.fromhex(treasure_map_id)
            this_node.treasure_maps[treasure_map_index] = treasure_map
            return Response(bytes(treasure_map), status=202)
        else:
            # TODO: Make this a proper 500 or whatever.  #341
            log.info("Bad TreasureMap ID; not storing {}".format(treasure_map_id))
            assert False

    @rest_app.route('/status/', methods=['GET'])
    def status():

        if request.args.get('json'):
            payload = this_node.abridged_node_details()
            response = jsonify(payload)
            return response

        else:
            headers = {"Content-Type": "text/html", "charset": "utf-8"}
            previous_states = list(reversed(this_node.known_nodes.states.values()))[:5]
            # Mature every known node before rendering.
            for node in this_node.known_nodes:
                node.mature()

            try:
                content = status_template.render(this_node=this_node,
                                                 known_nodes=this_node.known_nodes,
                                                 previous_states=previous_states,
                                                 domains=serving_domains,
                                                 version=nucypher.__version__,
                                                 checksum_address=this_node.checksum_address)
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
            # TODO: Design decision here: if they do pass both, and they're identical, do we let that slide?  NRN
            raise ValueError("Pass either a public_certificate or a public_certificate_filepath, not both.")

        if public_certificate:
            kwargs['keypair'] = HostingKeypair(certificate=public_certificate, host=host)
        elif public_certificate_filepath:
            kwargs['keypair'] = HostingKeypair(certificate_filepath=public_certificate_filepath, host=host)
        super().__init__(*args, **kwargs)
