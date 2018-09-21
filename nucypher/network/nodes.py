import OpenSSL
from constant_sorrow import constants
from eth_keys.datatypes import Signature as EthSignature

from nucypher.crypto.api import _save_tls_certificate
from nucypher.crypto.powers import BlockchainPower, SigningPower, EncryptingPower, NoSigningPower
from nucypher.network.protocols import SuspiciousActivity
from nucypher.network.server import TLSHostingPower
from nucypher.utilities.sandbox.constants import TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD


class VerifiableNode:

    _evidence_of_decentralized_identity = constants.NOT_SIGNED
    verified_stamp = False
    verified_interface = False
    _verified_node = False

    def __init__(self,
                 interface_signature=constants.NOT_SIGNED.bool_value(False),
                 certificate_filepath: str = None,
                 ) -> None:

        self.certificate_filepath = certificate_filepath  # TODO: This gets messy when it is None (although it being None is actually reasonable in some cases, at least for testing).  Let's make this a method instead that inspects the TLSHostingPower (similar to get_deployer()).
        self._interface_signature_object = interface_signature

    class InvalidNode(SuspiciousActivity):
        """
        Raised when a node has an invalid characteristic - stamp, interface, or address.
        """

    class WrongMode(TypeError):
        """
        Raise when a Character tries to use another Character as decentralized when the latter is federated_only.
        """

    def _stamp_has_valid_wallet_signature(self):
        signature_bytes = self._evidence_of_decentralized_identity
        if signature_bytes is constants.NOT_SIGNED:
            return False
        else:
            signature = EthSignature(signature_bytes)
        proper_pubkey = signature.recover_public_key_from_msg(bytes(self.stamp))
        proper_address = proper_pubkey.to_checksum_address()
        return proper_address == self.checksum_public_address

    def stamp_is_valid(self):
        """
        :return:
        """
        signature = self._evidence_of_decentralized_identity
        if self._stamp_has_valid_wallet_signature():
            self.verified_stamp = True
            return True
        elif self.federated_only and signature is constants.NOT_SIGNED:
            raise self.WrongMode("This node can't be verified in this manner, but is OK to use in federated mode if you have reason to believe it is trustworthy.")
        else:
            raise self.InvalidNode

    def interface_is_valid(self):
        """
        Checks that the interface info is valid for this node's canonical address.
        """
        message = self._signable_interface_info_message()  # Contains canonical address.
        interface_is_valid = self._interface_signature.verify(message, self.public_keys(SigningPower))
        self.verified_interface = interface_is_valid
        if interface_is_valid:
            return True
        else:
            raise self.InvalidNode

    def verify_id(self, ursula_id, digest_factory=bytes):
        self.verify()
        if not ursula_id == digest_factory(self.canonical_public_address):
            raise self.InvalidNode

    def validate_metadata(self, accept_federated_only=False):
        if not self.verified_interface:
            self.interface_is_valid()
        if not self.verified_stamp:
            try:
                self.stamp_is_valid()
            except self.WrongMode:
                if not accept_federated_only:
                    raise

    def verify_node(self, network_middleware, accept_federated_only=False, force=False):
        """
        Three things happening here:

        * Verify that the stamp matches the address (raises InvalidNode is it's not valid, or WrongMode if it's a federated mode and being verified as a decentralized node)
        * Verify the interface signature (raises InvalidNode if not valid)
        * Connect to the node, make sure that it's up, and that the signature and address we checked are the same ones this node is using now. (raises InvalidNode if not valid; also emits a specific warning depending on which check failed).
        """
        if not force:
            if self._verified_node:
                return True

        self.validate_metadata(accept_federated_only)  # This is both the stamp and interface check.

        # The node's metadata is valid; let's be sure the interface is in order.
        response = network_middleware.node_information(host=self.rest_information()[0].host,
                                                       port=self.rest_information()[0].port)
        if not response.status_code == 200:
            raise RuntimeError("Or something.")  # TODO: Raise an error here?  Or return False?  Or something?
        signature, identity_evidence, verifying_key, encrypting_key, public_address, certificate_vbytes, rest_info = self._internal_splitter(response.content)

        verifying_keys_match = verifying_key == self.public_keys(SigningPower)
        encrypting_keys_match = encrypting_key == self.public_keys(EncryptingPower)
        addresses_match = public_address == self.canonical_public_address
        evidence_matches = identity_evidence == self._evidence_of_decentralized_identity

        if not all((encrypting_keys_match, verifying_keys_match, addresses_match, evidence_matches)):
            # TODO: Optional reporting.  355
            if not addresses_match:
                self.log.warning("Wallet address swapped out.  It appears that someone is trying to defraud this node.")
            if not verifying_keys_match:
                self.log.warning("Verifying key swapped out.  It appears that someone is impersonating this node.")
            raise self.InvalidNode("Wrong cryptographic material for this node - something fishy going on.")

    def substantiate_stamp(self):
        blockchain_power = self._crypto_power.power_ups(BlockchainPower)
        blockchain_power.unlock_account(password=TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD)  # TODO: 349
        signature = blockchain_power.sign_message(bytes(self.stamp))
        self._evidence_of_decentralized_identity = signature

    def _signable_interface_info_message(self):
        message = self.canonical_public_address + self.rest_information()[0]
        return message

    def _sign_interface_info(self):
        message = self._signable_interface_info_message()
        self._interface_signature_object = self.stamp(message)

    @property
    def _interface_signature(self):
        if not self._interface_signature_object:
            try:
                self._sign_interface_info()
            except NoSigningPower:
                raise NoSigningPower("This Ursula is a Stranger; you didn't init with an interface signature, so you can't verify.")
        return self._interface_signature_object

    def certificate(self):
        return self._crypto_power.power_ups(TLSHostingPower).keypair.certificate

    def save_certificate_to_disk(self, directory):
        x509 = OpenSSL.crypto.X509.from_cryptography(self.certificate())
        subject_components = x509.get_subject().get_components()
        common_name_as_bytes = subject_components[0][1]
        common_name_from_cert = common_name_as_bytes.decode()
        if not self.checksum_public_address == common_name_from_cert:
            # TODO: It's better for us to have checked this a while ago so that this situation is impossible.  #443
            raise ValueError(
                "You passed a common_name that is not the same one as the cert.  Why?  FWIW, You don't even need to pass a common name here; the cert will be saved according to the name on the cert itself.")

        certificate_filepath = "{}/{}".format(directory,
                                              common_name_from_cert)  # TODO: Do this with proper path tooling.
        _save_tls_certificate(self.certificate(), full_filepath=certificate_filepath)

        self.certificate_filepath = certificate_filepath