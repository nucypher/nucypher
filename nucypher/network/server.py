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


import uuid
import weakref
from pathlib import Path
from typing import Tuple

from constant_sorrow import constants
from constant_sorrow.constants import RELAX, NOT_STAKING
from flask import Flask, Response, jsonify, request
from mako import exceptions as mako_exceptions
from mako.template import Template

from nucypher.core import (
    AuthorizedKeyFrag,
    ReencryptionRequest,
    Arrangement,
    ArrangementResponse,
    RevocationOrder,
    NodeMetadata,
    MetadataRequest,
    MetadataResponse,
    )

from nucypher.blockchain.eth.utils import period_to_epoch
from nucypher.config.constants import MAX_UPLOAD_CONTENT_LENGTH
from nucypher.crypto.keypairs import DecryptingKeypair
from nucypher.crypto.powers import KeyPairBasedPower, PowerUpError
from nucypher.crypto.signing import InvalidSignature
from nucypher.datastore.datastore import Datastore
from nucypher.datastore.models import ReencryptionRequest as ReencryptionRequestModel
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.protocols import InterfaceInfo
from nucypher.network.nodes import NodeSprout
from nucypher.utilities.logging import Logger

HERE = BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = HERE / "templates"

status_template = Template(filename=str(TEMPLATES_DIR / "basic_status.mako")).get_def('main')


class ProxyRESTServer:

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
        db_filepath: Path,
        this_node,
        domain,
        log: Logger = Logger("http-application-layer")
        ) -> Tuple[Flask, Datastore]:
    """
    Creates a REST application and an associated ``Datastore`` object.
    Note that the REST app **does not** hold a reference to the datastore;
    it is your responsibility to ensure it lives for as long as the app does.
    """

    # A trampoline function for the real REST app,
    # to ensure that a reference to the node and the datastore object is not held by the app closure.
    # One would think that it's enough to only remove a reference to the node,
    # but `rest_app` somehow holds a reference to itself, Uroboros-like,
    # and will hold the datastore reference if it is created there.

    log.info("Starting datastore {}".format(db_filepath))
    datastore = Datastore(db_filepath)
    rest_app = _make_rest_app(weakref.proxy(datastore), weakref.proxy(this_node), domain, log)

    return rest_app, datastore


def _make_rest_app(datastore: Datastore, this_node, domain: str, log: Logger) -> Flask:

    # TODO: Avoid circular imports :-(
    from nucypher.characters.lawful import Alice, Bob, Ursula
    from nucypher.policy.policies import Policy

    _alice_class = Alice
    _bob_class = Bob
    _node_class = Ursula

    rest_app = Flask("ursula-service")
    rest_app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_CONTENT_LENGTH

    @rest_app.route("/public_information")
    def public_information():
        """REST endpoint for public keys and address."""
        response = Response(response=bytes(this_node.metadata()), mimetype='application/octet-stream')
        return response

    @rest_app.route('/node_metadata', methods=["GET"])
    def all_known_nodes():
        headers = {'Content-Type': 'application/octet-stream'}
        if this_node._learning_deferred is not RELAX and not this_node._learning_task.running:
            # Learn when learned about
            this_node.start_learning_loop()

        # All known nodes + this node
        response_bytes = this_node.bytestring_of_known_nodes()
        return Response(response_bytes, headers=headers)

    @rest_app.route('/node_metadata', methods=["POST"])
    def node_metadata_exchange():

        metadata_request = MetadataRequest.from_bytes(request.data)

        # If these nodes already have the same fleet state, no exchange is necessary.

        learner_fleet_state = request.args.get('fleet')
        if metadata_request.fleet_state_checksum == this_node.known_nodes.checksum:
            # log.debug("Learner already knew fleet state {}; doing nothing.".format(learner_fleet_state))  # 1712
            headers = {'Content-Type': 'application/octet-stream'}
            # No nodes in the response: same fleet state
            response = MetadataResponse.author(signer=this_node.stamp.as_umbral_signer(),
                                               timestamp_epoch=this_node.known_nodes.timestamp.epoch)
            return Response(bytes(response), headers=headers)

        if metadata_request.announce_nodes:
            for node in metadata_request.announce_nodes:
                this_node.remember_node(NodeSprout(node))

        # TODO: generate a new fleet state here?

        # TODO: What's the right status code here?  202?  Different if we already knew about the node(s)?
        return all_known_nodes()

    @rest_app.route('/consider_arrangement', methods=['POST'])
    def consider_arrangement():
        arrangement = Arrangement.from_bytes(request.data)

        # Verify this node is staking for the entirety of the proposed arrangement.
        if not this_node.federated_only:

            # Get final staking period
            if this_node.stakes.terminal_period is NOT_STAKING:
                this_node.stakes.refresh()
            if this_node.stakes.terminal_period is NOT_STAKING:
                return Response(status=403)  # 403 Forbidden

            # Verify timeframe
            terminal_stake_period = this_node.stakes.terminal_period
            terminal_stake_epoch = period_to_epoch(period=terminal_stake_period,
                                                   seconds_per_period=this_node.economics.seconds_per_period)
            if arrangement.expiration_epoch > terminal_stake_epoch:
                # I'm sorry David, I'm afraid I can't do that.
                return Response(status=403)  # 403 Forbidden

        response = ArrangementResponse.for_arrangement(arrangement, this_node.stamp.as_umbral_signer())
        headers = {'Content-Type': 'application/octet-stream'}
        return Response(bytes(response), status=200, headers=headers)

    @rest_app.route('/reencrypt', methods=["POST"])
    def reencrypt():

        from nucypher.characters.lawful import Bob

        # TODO: Cache & Optimize

        reenc_request = ReencryptionRequest.from_bytes(request.data)
        hrac = reenc_request.hrac
        bob = Bob.from_public_keys(verifying_key=reenc_request.bob_verifying_key)
        log.info(f"Work Order from {bob} for policy {hrac}")

        # Right off the bat, if this HRAC is already known to be revoked, reject the order.
        if hrac in this_node.revoked_policies:
            return Response(response="Invalid KFrag sender.", status=401)  # 401 - Unauthorized

        # Alice & Publisher
        author_verifying_key = reenc_request.alice_verifying_key
        publisher_verifying_key = reenc_request.publisher_verifying_key

        # Bob
        bob_ip_address = request.remote_addr
        bob_verifying_key = bob.stamp.as_umbral_pubkey()
        bob_identity_message = f"[{bob_ip_address}] Bob({bytes(bob.stamp).hex()})"

        # Verify & Decrypt KFrag Payload
        try:
            authorized_kfrag = this_node._decrypt_kfrag(encrypted_kfrag=reenc_request.encrypted_kfrag,
                                                        author_verifying_key=author_verifying_key)
        except ValueError as e:
            message = f'{bob_identity_message} Invalid AuthorizedKeyFrag: {e}.'
            log.info(message)
            this_node.suspicious_activities_witnessed['unauthorized'].append(message)
            return Response(message, status=400)  # 400 - General error
        except InvalidSignature:
            # TODO: don't we want to record suspicious activities here too?
            return Response(response="Invalid KFrag sender.", status=401)  # 401 - Unauthorized
        except DecryptingKeypair.DecryptionFailed:
            return Response(response="KFrag decryption failed.", status=403)   # 403 - Forbidden

        # Verify KFrag Authorization (offchain)
        try:
            verified_kfrag = this_node.verify_kfrag_authorization(hrac=reenc_request.hrac,
                                                                  author_verifying_key=author_verifying_key,
                                                                  publisher_verifying_key=publisher_verifying_key,
                                                                  authorized_kfrag=authorized_kfrag)

        except Policy.Unauthorized:
            message = f'{bob_identity_message} Unauthorized work order.'
            log.info(message)
            this_node.suspicious_activities_witnessed['unauthorized'].append(message)
            return Response(message, status=401)  # 401 - Unauthorized

        if not this_node.federated_only:

            # Verify Policy Payment (onchain)
            try:
                this_node.verify_policy_payment(hrac=hrac)
            except Policy.Unpaid:
                message = f"{bob_identity_message} Policy {hrac} is unpaid."
                record = (policy_publisher, message)
                this_node.suspicious_activities_witnessed['freeriders'].append(record)
                return Response(message, status=402)  # 402 - Payment Required
            except Policy.Unknown:
                message = f"{bob_identity_message} Policy {hrac} is not a published policy."
                return Response(message, status=404)  # 404 - Not Found

            # Verify Active Policy (onchain)
            try:
                this_node.verify_active_policy(hrac=hrac)
            except Policy.Inactive:
                message = f"{bob_identity_message} Policy {hrac} is not active."
                return Response(message, status=403)  # 403 - Forbidden
            except this_node.PolicyInfo.Expired:
                message = f"{bob_identity_message} Policy {hrac} is expired."
                return Response(message, status=403)  # 403 - Forbidden

        # Re-encrypt
        # TODO: return a sensible response if it fails
        response = this_node._reencrypt(kfrag=verified_kfrag,
                                        capsules=reenc_request.capsules)

        # Now, Ursula saves evidence of this workorder to her database...
        # Note: we give the work order a random ID to store it under.
        with datastore.describe(ReencryptionRequestModel, str(uuid.uuid4()), writeable=True) as new_request:
            new_request.bob_verifying_key = bob_verifying_key

        headers = {'Content-Type': 'application/octet-stream'}
        return Response(headers=headers, response=bytes(response))

    @rest_app.route('/revoke', methods=['POST'])
    def revoke():
        revocation = RevocationOrder.from_bytes(request.data)
        # TODO: Implement offchain revocation.
        return Response(status=200)

    @rest_app.route("/ping", methods=['GET', 'POST'])
    def ping():
        """
        GET: Asks this node: "What is my IP address?"
        POST: Asks this node: "Can you access my public information endpoint?"
        """

        if request.method == 'GET':
            requester_ip_address = request.remote_addr
            return Response(requester_ip_address, status=200)

        elif request.method == 'POST':
            try:
                requester_metadata = NodeMetadata.from_bytes(request.data)
                requesting_ursula = NodeSprout(requester_metadata)
                requesting_ursula.mature()
            except ValueError:
                return Response({'error': 'Invalid Ursula'}, status=400)
            else:
                initiator_address, initiator_port = tuple(requesting_ursula.rest_interface)

            # Compare requester and posted Ursula information
            request_address = request.remote_addr
            if request_address != initiator_address:
                message = f'Origin address mismatch: Request origin is {request_address} but metadata claims {initiator_address}.'
                return Response({'error': message}, status=400)

            #
            # Make a Sandwich
            #

            try:
                # Fetch and store initiator's teacher certificate.
                certificate = this_node.network_middleware.get_certificate(host=initiator_address, port=initiator_port)
                certificate_filepath = this_node.node_storage.store_node_certificate(certificate=certificate)
                metadata_bytes = this_node.network_middleware.client.node_information(host=initiator_address,
                                                                                      port=initiator_port,
                                                                                      certificate_filepath=certificate_filepath)
                visible_metadata = NodeMetadata.from_bytes(metadata_bytes)
            except NodeSeemsToBeDown:
                return Response({'error': 'Unreachable node'}, status=400)  # ... toasted

            if requester_metadata == visible_metadata:
                return Response(status=200)
            else:
                return Response({'error': 'Suspicious node'}, status=400)

    @rest_app.route('/status/', methods=['GET'])
    def status():
        return_json = request.args.get('json') == 'true'
        omit_known_nodes = request.args.get('omit_known_nodes') == 'true'
        status_info = this_node.status_info(omit_known_nodes=omit_known_nodes)
        if return_json:
            return jsonify(status_info.to_json())
        headers = {"Content-Type": "text/html", "charset": "utf-8"}
        try:
            content = status_template.render(status_info)
        except Exception as e:
            text_error = mako_exceptions.text_error_template().render()
            html_error = mako_exceptions.html_error_template().render()
            log.debug("Template Rendering Exception:\n" + text_error)
            return Response(response=html_error, headers=headers, status=500)
        return Response(response=content, headers=headers)

    return rest_app
