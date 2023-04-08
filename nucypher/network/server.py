import json
import weakref
from http import HTTPStatus

from ferveo_py import Ciphertext
from pathlib import Path

from constant_sorrow import constants
from constant_sorrow.constants import RELAX
from flask import Flask, Response, jsonify, request
from mako import exceptions as mako_exceptions
from mako.template import Template

from nucypher.policy.conditions.lingo import ConditionLingo
from nucypher.utilities.mock import ThresholdDecryptionRequest, ThresholdDecryptionResponse
from nucypher_core import (
    MetadataRequest,
    MetadataResponse,
    MetadataResponsePayload,
    ReencryptionRequest,
    RevocationOrder,
)

from nucypher.config.constants import MAX_UPLOAD_CONTENT_LENGTH
from nucypher.crypto.keypairs import DecryptingKeypair
from nucypher.crypto.signing import InvalidSignature
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.nodes import NodeSprout
from nucypher.network.protocols import InterfaceInfo
from nucypher.policy.conditions.rust_shims import _deserialize_rust_lingos
from nucypher.policy.conditions.utils import evaluate_condition_lingo
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
                 rest_app=None
                 ) -> None:

        self.rest_interface = InterfaceInfo(host=rest_host, port=rest_port)
        if rest_app:  # if is me
            self.rest_app = rest_app
        else:
            self.rest_app = constants.PUBLIC_ONLY

        self.__hosting_power = hosting_power

    def rest_url(self):
        return "{}:{}".format(self.rest_interface.host, self.rest_interface.port)


def make_rest_app(
        this_node,
        log: Logger = Logger("http-application-layer")
        ) -> Flask:
    """Creates a REST application."""

    # A trampoline function for the real REST app,
    # to ensure that a reference to the node object is not held by the app closure.
    # One would think that it's enough to only remove a reference to the node,
    # but `rest_app` somehow holds a reference to itself, Uroboros-like...
    rest_app = _make_rest_app(weakref.proxy(this_node), log)
    return rest_app


def _make_rest_app(this_node, log: Logger) -> Flask:

    # TODO: Avoid circular imports :-(
    from nucypher.characters.lawful import Alice, Bob, Ursula

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
            response_payload = MetadataResponsePayload(timestamp_epoch=this_node.known_nodes.timestamp.epoch,
                                                       announce_nodes=[])
            response = MetadataResponse(this_node.stamp.as_umbral_signer(),
                                        response_payload)
            return Response(bytes(response), headers=headers)

        if metadata_request.announce_nodes:
            for metadata in metadata_request.announce_nodes:
                try:
                    metadata.verify()
                except Exception:
                    # inconsistent metadata
                    pass
                else:
                    this_node.remember_node(NodeSprout(metadata))

        # TODO: generate a new fleet state here?

        # TODO: What's the right status code here?  202?  Different if we already knew about the node(s)?
        return all_known_nodes()

    @rest_app.route('/decrypt', methods=["POST"])
    def threshold_decrypt():

        # Deserialize and instantiate ThresholdDecryptionRequest from the request data
        decryption_request = ThresholdDecryptionRequest.from_bytes(request.data)

        # Deserialize and instantiate ConditionLingo from the request data
        lingo = ConditionLingo.from_list(json.loads(str(decryption_request.conditions)))

        # requester-supplied condition eval context
        context = None
        if decryption_request.context:
            context = json.loads(str(decryption_request.context)) or dict()

        # evaluate the conditions for this ciphertext
        error = evaluate_condition_lingo(lingo, context)
        if error:
            return Response(error.message, status=error.status_code)

        # derive the decryption share
        decryption_share = this_node.derive_decryption_share(
            ritual_id=decryption_request.ritual_id,
            ciphertext=decryption_request.ciphertext,
            conditions=decryption_request.conditions,
        )

        # return the decryption share
        response = ThresholdDecryptionResponse(decryption_share=decryption_share)
        return Response(bytes(response), headers={'Content-Type': 'application/octet-stream'})

    @rest_app.route('/reencrypt', methods=["POST"])
    def reencrypt():
        # TODO: Cache & Optimize
        from nucypher.characters.lawful import Bob

        # Deserialize and instantiate the request
        reenc_request = ReencryptionRequest.from_bytes(request.data)

        # Deserialize and instantiate ConditionLingo from the request data
        lingos = _deserialize_rust_lingos(reenc_request=reenc_request)

        # requester-supplied reencryption condition context
        context = json.loads(str(reenc_request.context)) or dict()

        # zip capsules with their respective conditions
        packets = zip(reenc_request.capsules, lingos)

        # TODO: Detect if we are dealing with PRE or tDec here
        # TODO: This is for PRE only, relocate HRAC to RE.context
        hrac = reenc_request.hrac

        # This is either PRE Bob or a CBD requester
        bob = Bob.from_public_keys(verifying_key=reenc_request.bob_verifying_key)
        log.info(f"Reencryption request from {bob} for policy {hrac}")

        # TODO: Can this be integrated into reencryption conditions?
        # Stateful revocation by HRAC storage below
        if hrac in this_node.revoked_policies:
            return Response(response=f"Policy with {hrac} has been revoked.", status=HTTPStatus.UNAUTHORIZED)

        # Alice or Publisher
        publisher_verifying_key = reenc_request.publisher_verifying_key

        # Bob
        bob_ip_address = request.remote_addr
        bob_identity_message = f"[{bob_ip_address}] Bob({bytes(bob.stamp).hex()})"

        # Verify & Decrypt KFrag Payload
        try:
            verified_kfrag = this_node._decrypt_kfrag(
                reenc_request.encrypted_kfrag,
                hrac,
                publisher_verifying_key
            )
        except DecryptingKeypair.DecryptionFailed as e:
            # TODO: don't we want to record suspicious activities here too?
            return Response(
                response=f"EncryptedKeyFrag decryption failed: {e}",
                status=HTTPStatus.FORBIDDEN,
            )
        except InvalidSignature as e:
            message = f'{bob_identity_message} Invalid signature for KeyFrag: {e}.'
            log.info(message)
            # TODO (#567): bucket the node as suspicious
            return Response(message, status=HTTPStatus.UNAUTHORIZED)  # 401 - Unauthorized
        except Exception as e:
            message = f'{bob_identity_message} Invalid EncryptedKeyFrag: {e}.'
            log.info(message)
            # TODO (#567): bucket the node as suspicious.
            return Response(message, status=HTTPStatus.BAD_REQUEST)

        # Enforce Reencryption Conditions
        capsules_to_process = list()
        for capsule, condition_lingo in packets:
            if condition_lingo:
                error = evaluate_condition_lingo(
                    lingo=condition_lingo,
                    providers=this_node.condition_providers,
                    context=context
                )
                if error:
                    # TODO: This response short-circuits the entire request on falsy condition
                    #  even if other unrelated capsules (message kits) are present.
                    return Response(error.message, status=error.status_code)
            capsules_to_process.append(capsule)

        # FIXME: DISABLED FOR PRE-adapted-TDEC
        # TODO: Accept multiple payment methods?
        # Subscription Manager
        # paid = this_node.payment_method.verify(payee=this_node.checksum_address, request=reenc_request)
        # if not paid:
        #     message = f"{bob_identity_message} Policy {bytes(hrac)} is unpaid."
        #     return Response(message, status=HTTPStatus.PAYMENT_REQUIRED)

        # Re-encrypt
        # TODO: return a sensible response if it fails (currently results in 500)
        response = this_node._reencrypt(kfrag=verified_kfrag, capsules=capsules_to_process)

        headers = {'Content-Type': 'application/octet-stream'}
        return Response(headers=headers, response=bytes(response))

    @rest_app.route('/revoke', methods=['POST'])
    def revoke():
        revocation = RevocationOrder.from_bytes(request.data)
        # TODO: Implement off-chain revocation.
        return Response(status=HTTPStatus.OK)

    @rest_app.route("/ping", methods=['GET'])
    def ping():
        """Asks this node: What is my IP address?"""
        requester_ip_address = request.remote_addr
        return Response(requester_ip_address, status=HTTPStatus.OK)

    @rest_app.route("/check_availability", methods=['POST'])
    def check_availability():
        """Asks this node: Can you access my public information endpoint?"""
        try:
            requesting_ursula = Ursula.from_metadata_bytes(request.data)
            requesting_ursula.mature()
        except ValueError:
            return Response({'error': 'Invalid Ursula'}, status=HTTPStatus.BAD_REQUEST)
        else:
            initiator_address, initiator_port = tuple(requesting_ursula.rest_interface)

        # Compare requester and posted Ursula information
        request_address = request.remote_addr
        if request_address != initiator_address:
            message = f'Origin address mismatch: Request origin is {request_address} but metadata claims {initiator_address}.'
            return Response({'error': message}, status=HTTPStatus.BAD_REQUEST)

        # Make a Sandwich
        try:
            requesting_ursula_metadata = this_node.network_middleware.client.node_information(
                host=initiator_address,
                port=initiator_port,
            )
        except NodeSeemsToBeDown:
            return Response({'error': 'Unreachable node'}, status=HTTPStatus.BAD_REQUEST)  # ... toasted

        # Compare the results of the outer POST with the inner GET... yum
        if requesting_ursula_metadata == request.data:
            return Response(status=HTTPStatus.OK)
        else:
            return Response({'error': 'Suspicious node'}, status=HTTPStatus.BAD_REQUEST)

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
            return Response(response=html_error, headers=headers, status=HTTPStatus.INTERNAL_SERVER_ERROR)
        return Response(response=content, headers=headers)

    return rest_app
