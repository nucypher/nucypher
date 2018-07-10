from nucypher.crypto.powers import BlockchainPower, SigningPower, EncryptingPower
from constant_sorrow import constants
from nucypher.network.protocols import SuspiciousActivity


class VerifiableNode:

    _evidence_of_decentralized_identity = constants.NOT_SIGNED
    verified_stamp = False
    verified_interface = False
    _verified_node = False

    def __init__(self, interface_signature):
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
        signature = self._evidence_of_decentralized_identity
        if signature is constants.NOT_SIGNED:
            return False
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
        message = self._signable_interface_info_message()
        interface_is_valid = self._interface_signature.verify(message, self.public_key(SigningPower))
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
        if not force:
            if self._verified_node:
                return True

        self.validate_metadata(accept_federated_only)

        # The node's metadata is valid; let's be sure the interface is in order.
        response = network_middleware.node_information(host=self.rest_interface.host,
                                            port=self.rest_interface.port)
        if not response.status_code == 200:
            raise RuntimeError("Or something.")  # TODO: Raise an error here?  Or return False?  Or something?
        signature, verifying_key, encrypting_key, canonical_address = self.public_information_splitter(response.content)

        verifying_keys_match = verifying_key == self.public_key(SigningPower)
        encrypting_keys_match = encrypting_key == self.public_key(EncryptingPower)
        addresses_match = canonical_address == self.canonical_public_address

        if not all((encrypting_keys_match, verifying_keys_match, addresses_match)):
            # TODO: Optional reporting.  355
            if not addresses_match:
                self.log.warning("Wallet address swapped out.  It appears that someone is trying to defraud this node.")
            if not verifying_keys_match:
                self.log.warning("Verifying key swapped out.  It appears that someone is impersonating this node.")
            raise self.InvalidNode("Wrong cryptographic material for this node - something fishy going on.")

        verified = signature.verify(message=response.content[len(signature):], verifying_key=verifying_key)

        if verified:
            self._verified_node = True
            return True
        else:
            raise self.InvalidNode("Node signature was invalid after all.  It may be misconfigured, or this may be an attack.")

    def substantiate_stamp(self):
        blockchain_power = self._crypto_power.power_ups(BlockchainPower)
        blockchain_power.unlock_account('this-is-not-a-secure-password')  # TODO: 349
        signature = blockchain_power.sign_message(bytes(self.stamp))
        self._evidence_of_decentralized_identity = signature

    def _signable_interface_info_message(self):
        message = self.canonical_public_address + self.rest_interface + self.dht_interface
        return message

    def _sign_interface_info(self):
        message = self._signable_interface_info_message()
        self._interface_signature_object = self.stamp(message)

    @property
    def _interface_signature(self):
        if not self._interface_signature_object:
            self._sign_interface_info()
        return self._interface_signature_object
