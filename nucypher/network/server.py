import json
import weakref
from http import HTTPStatus
from ipaddress import AddressValueError
from pathlib import Path
from typing import Optional

from constant_sorrow import constants
from flask import Flask, Response, jsonify, request
from hexbytes import HexBytes
from mako import exceptions as mako_exceptions
from mako.template import Template
from nucypher_core import (
    EncryptedThresholdDecryptionRequest,
    MetadataRequest,
    MetadataResponse,
    MetadataResponsePayload,
    ReencryptionRequest,
)
from prometheus_client import REGISTRY, Counter, Summary

from nucypher.blockchain.eth import domains
from nucypher.config.constants import MAX_UPLOAD_CONTENT_LENGTH, TEMPORARY_DOMAIN_NAME
from nucypher.crypto.keypairs import DecryptingKeypair
from nucypher.crypto.signing import InvalidSignature
from nucypher.network.nodes import NodeSprout
from nucypher.network.protocols import InterfaceInfo
from nucypher.policy.conditions.exceptions import InvalidConditionLingo
from nucypher.policy.conditions.lingo import ConditionLingo
from nucypher.policy.conditions.utils import (
    ConditionEvalError,
    evaluate_condition_lingo,
)
from nucypher.utilities.logging import Logger
from nucypher.utilities.networking import get_global_source_ipv4

# Prometheus metrics
DECRYPTION_REQUESTS_SUCCESSES = Counter(
    "threshold_decryption_num_successes",
    "Number of threshold decryption successes",
    registry=REGISTRY,
)
DECRYPTION_REQUESTS_FAILURES = Counter(
    "threshold_decryption_num_failures",
    "Number of threshold decryption failures",
    registry=REGISTRY,
)

# Summary provides both `count` (num of calls), and `sum` (time taken in method)
DECRYPTION_REQUEST_SUMMARY = Summary(
    "decryption_request_processing",
    "Summary of decryption request processing",
    registry=REGISTRY,
)

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

    @rest_app.route('/node_metadata', methods=["POST"])
    def node_metadata_exchange():
        try:
            metadata_request = MetadataRequest.from_bytes(request.data)
        except ValueError as e:
            # this line is hit when the MetadataRequest is an old version
            # ValueError: Failed to deserialize: differing major version: expected 3, got 1
            return Response(str(e), status=HTTPStatus.BAD_REQUEST)

        # If these nodes already have the same fleet state, no exchange is necessary.
        response_headers = {"Content-Type": "application/octet-stream"}

        if metadata_request.fleet_state_checksum == this_node.known_nodes.checksum:
            # log.debug("Learner already knew fleet state {}; doing nothing.".format(learner_fleet_state))  # 1712
            # No nodes in the response: same fleet state
            response_payload = MetadataResponsePayload(timestamp_epoch=this_node.known_nodes.timestamp.epoch,
                                                       announce_nodes=[])
            response = MetadataResponse(this_node.stamp.as_umbral_signer(),
                                        response_payload)
            return Response(bytes(response), headers=response_headers)

        if metadata_request.announce_nodes:
            for metadata in metadata_request.announce_nodes:
                try:
                    metadata.verify()
                except Exception:
                    # inconsistent metadata
                    pass
                else:
                    this_node.remember_node(NodeSprout(metadata))

        # All known nodes + this node
        response_bytes = this_node.bytestring_of_known_nodes()
        response = Response(
            response_bytes, headers=response_headers, status=HTTPStatus.OK
        )
        return response

    @rest_app.route("/condition_chains", methods=["GET"])
    def condition_chains():
        """
        An endpoint that returns the condition evaluation blockchains
        this node has connected to.
        """
        # TODO: When non-evm chains are supported, bump the version.
        #  this can return a list of chain names or other verifiable identifiers.
        providers = this_node.condition_provider_manager.providers
        sorted_chain_ids = sorted(list(providers))
        payload = {"version": 1.0, "evm": sorted_chain_ids}
        return Response(json.dumps(payload), mimetype="application/json")

    @rest_app.route('/decrypt', methods=["POST"])
    @DECRYPTION_REQUEST_SUMMARY.time()
    def threshold_decrypt():
        try:
            with DECRYPTION_REQUESTS_FAILURES.count_exceptions():
                encrypted_request = EncryptedThresholdDecryptionRequest.from_bytes(
                    request.data
                )
                encrypted_response = this_node.handle_threshold_decryption_request(
                    encrypted_request
                )

            DECRYPTION_REQUESTS_SUCCESSES.inc()
            response = Response(
                response=bytes(encrypted_response),
                status=HTTPStatus.OK,
                mimetype="application/octet-stream",
            )
            return response
        except this_node.RitualNotFoundException:
            return Response("Ritual not found", status=HTTPStatus.NOT_FOUND)
        except this_node.UnauthorizedRequest as e:
            return Response(str(e), status=HTTPStatus.UNAUTHORIZED)
        except ConditionEvalError as e:
            return Response(e.message, status=e.status_code)
        except this_node.DecryptionFailure as e:
            return Response(str(e), status=HTTPStatus.INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response(str(e), status=HTTPStatus.INTERNAL_SERVER_ERROR)

    @rest_app.route('/reencrypt', methods=["POST"])
    def reencrypt():
        # TODO: Cache & Optimize
        from nucypher.characters.lawful import Bob

        # Deserialize and instantiate the request
        reenc_request = ReencryptionRequest.from_bytes(request.data)

        # obtain conditions from request
        lingo_list = json.loads(
            str(reenc_request.conditions)
        )  # Conditions -> str -> List[Lingo]

        # requester-supplied reencryption condition context
        context = json.loads(str(reenc_request.context)) or dict()

        # zip capsules with their respective conditions
        packets = zip(reenc_request.capsules, lingo_list)

        # TODO: Relocate HRAC to RE.context
        hrac = reenc_request.hrac

        # This is either PRE Bob or a CBD requester
        bob = Bob.from_public_keys(verifying_key=reenc_request.bob_verifying_key)
        log.info(f"Reencryption request from {bob} for policy {hrac}")

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

        # Enforce Subscription Manager Payment
        paid = this_node.pre_payment_method.verify(
            payee=this_node.checksum_address, request=reenc_request
        )
        if not paid:
            message = f"{bob_identity_message} Policy {bytes(hrac)} is unpaid."
            return Response(message, status=HTTPStatus.PAYMENT_REQUIRED)

        # Enforce Conditions
        capsules_to_process = list()
        for capsule, condition_lingo in packets:
            if condition_lingo:
                try:
                    evaluate_condition_lingo(
                        condition_lingo=condition_lingo,
                        providers=this_node.condition_provider_manager,
                        context=context,
                    )
                except ConditionEvalError as error:
                    # TODO: This response short-circuits the entire request on falsy condition
                    #  even if other unrelated capsules (message kits) are present.
                    return Response(error.message, status=error.status_code)
            capsules_to_process.append(capsule)

        # Re-encrypt
        # TODO: return a sensible response if it fails (currently results in 500)
        response = this_node._reencrypt(kfrag=verified_kfrag, capsules=capsules_to_process)

        headers = {'Content-Type': 'application/octet-stream'}
        return Response(headers=headers, response=bytes(response))

    @rest_app.route("/ping", methods=['GET'])
    def ping():
        """Asks this node: What is my public IPv4 address?"""
        try:
            ipv4 = get_global_source_ipv4(request=request)
        except AddressValueError as e:
            return Response(
                response=str(e),
                status=HTTPStatus.BAD_REQUEST,
            )
        if not ipv4:
            return Response(
                response="No public IPv4 address detected.",
                status=HTTPStatus.BAD_GATEWAY,
            )
        return Response(response=ipv4, status=HTTPStatus.OK)

    @rest_app.route("/status", methods=["GET"])
    def status():
        return_json = request.args.get('json') == 'true'
        omit_known_nodes = request.args.get('omit_known_nodes') == 'true'
        status_info = this_node.status_info(omit_known_nodes=omit_known_nodes)
        if return_json:
            return jsonify(status_info.to_json())
        headers = {"Content-Type": "text/html", "charset": "utf-8"}
        try:
            content = status_template.render(status_info)
        except Exception:
            text_error = mako_exceptions.text_error_template().render()
            html_error = mako_exceptions.html_error_template().render()
            log.debug("Template Rendering Exception:\n" + text_error)
            return Response(response=html_error, headers=headers, status=HTTPStatus.INTERNAL_SERVER_ERROR)
        return Response(response=content, headers=headers)

    @rest_app.route("/sign", methods=["POST"])
    def threshold_sign():
        """
        An endpoint that handles threshold signing requests.

        The request includes:
        - cohort_id: ID of the signing cohort
        - data_to_sign: The data to be signed
        - condition: Condition lingo for authorization (can be a compound of ECDSA and JSON API conditions)
        - context: Context variables for the condition lingo
        - proof_type: The type of proof
        - proof: The proof data
        - signature: Signature of the proof
        """
        try:
            signing_request = ThresholdSignatureRequest.from_bytes(request.data)

            # Evaluate condition if provided
            if signing_request.condition:
                try:
                    # Load the condition lingo
                    condition_lingo_json = signing_request.condition.decode()

                    try:
                        condition_lingo = ConditionLingo.from_json(condition_lingo_json)
                    except (
                        InvalidConditionLingo,
                        json.JSONDecodeError,
                        Exception,
                    ) as e:
                        log.error(f"Failed to load condition lingo: {e}")
                        return Response(
                            f"Invalid condition lingo: {e}",
                            status=HTTPStatus.BAD_REQUEST,
                        )

                    # Get the context from the request
                    context = (
                        json.loads(signing_request.context.decode())
                        if signing_request.context
                        else {}
                    )

                    # Evaluate the condition
                    try:
                        # Evaluate the condition with the provided context and this node's providers
                        is_authorized = condition_lingo.eval(
                            providers=this_node.condition_provider_manager, **context
                        )

                        if not is_authorized:
                            return Response(
                                "Condition not satisfied",
                                status=HTTPStatus.UNAUTHORIZED,
                            )
                    except Exception as e:
                        log.error(f"Error evaluating condition: {e}")
                        return Response(
                            f"Error evaluating condition: {e}",
                            status=HTTPStatus.INTERNAL_SERVER_ERROR,
                        )
                except ConditionEvalError as e:
                    return Response(e.message, status=e.status_code)

            # Handle the signing request after condition verification
            signing_response = this_node.handle_threshold_signing_request(
                signing_request.cohort_id,
                signing_request.data_to_sign,
                signing_request.proof_type,
                signing_request.proof,
                signing_request.signature,
            )

            return Response(
                response=bytes(signing_response),
                status=HTTPStatus.OK,
                mimetype="application/octet-stream",
            )
        except this_node.UnauthorizedRequest as e:
            return Response(str(e), status=HTTPStatus.UNAUTHORIZED)
        except Exception as e:
            return Response(str(e), status=HTTPStatus.INTERNAL_SERVER_ERROR)

    @rest_app.route("/health", methods=["GET"])
    def health_check():
        """Health check endpoint"""
        return jsonify({"status": "healthy"}), 200

    if this_node.domain.name in [domains.LYNX.name, TEMPORARY_DOMAIN_NAME]:
        # only available on Lynx or for testing
        @rest_app.route("/validate_condition_lingo", methods=["POST"])
        def validate_condition_lingo():
            """
            An endpoint that validates a condition lingo
            """
            try:
                _ = ConditionLingo.from_json(request.get_json())
                return jsonify({"status": "valid"}), HTTPStatus.OK
            except InvalidConditionLingo as e:
                return Response(str(e), status=HTTPStatus.BAD_REQUEST)

    return rest_app


class ThresholdSignatureRequest:
    def __init__(
        self,
        data_to_sign: bytes,
        cohort_id: int,
        condition: Optional[bytes] = None,
        context: Optional[bytes] = None,
        proof_type: Optional[str] = None,
        proof: Optional[bytes] = None,
        signature: Optional[bytes] = None,
    ):
        self.data_to_sign = data_to_sign
        self.cohort_id = cohort_id
        self.condition = condition
        self.context = context
        self.proof_type = proof_type
        self.proof = proof
        self.signature = signature

    @staticmethod
    def from_bytes(request_data: bytes):
        # Deserialize the request data
        result = json.loads(request_data.decode())

        # Extract required fields
        data_to_sign = bytes(HexBytes(result["data_to_sign"]))
        cohort_id = result["cohort_id"]

        # Extract optional fields
        condition = (
            bytes(HexBytes(result["condition"])) if "condition" in result else None
        )
        context = bytes(HexBytes(result["context"])) if "context" in result else None
        proof_type = result.get("proof_type")
        proof = bytes(HexBytes(result["proof"])) if "proof" in result else None
        signature = (
            bytes(HexBytes(result["signature"])) if "signature" in result else None
        )

        return ThresholdSignatureRequest(
            data_to_sign=data_to_sign,
            cohort_id=cohort_id,
            condition=condition,
            context=context,
            proof_type=proof_type,
            proof=proof,
            signature=signature,
        )
