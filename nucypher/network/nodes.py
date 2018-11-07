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
import os

import OpenSSL
import maya
from constant_sorrow import constants
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509 import Certificate, NameOID
from eth_keys.datatypes import Signature as EthSignature
from twisted.logger import Logger

from nucypher.config.constants import SeednodeMetadata
from nucypher.config.keyring import _write_tls_certificate
from nucypher.crypto.powers import BlockchainPower, SigningPower, EncryptingPower, NoSigningPower
from nucypher.network.middleware import RestMiddleware
from nucypher.network.protocols import SuspiciousActivity
from nucypher.network.server import TLSHostingPower


class VerifiableNode:
    _evidence_of_decentralized_identity = constants.NOT_SIGNED
    verified_stamp = False
    verified_interface = False
    _verified_node = False
    _interface_info_splitter = (int, 4, {'byteorder': 'big'})
    log = Logger("network/nodes")

    def __init__(self,
                 certificate: Certificate,
                 certificate_filepath: str,
                 interface_signature=constants.NOT_SIGNED.bool_value(False),
                 timestamp=constants.NOT_SIGNED,
                 ) -> None:

        self.certificate = certificate
        self.certificate_filepath = certificate_filepath
        self._interface_signature_object = interface_signature
        self._timestamp = timestamp

    class InvalidNode(SuspiciousActivity):
        """
        Raised when a node has an invalid characteristic - stamp, interface, or address.
        """

    class WrongMode(TypeError):
        """
        Raise when a Character tries to use another Character as decentralized when the latter is federated_only.
        """

    def seed_node_metadata(self):
        return SeednodeMetadata(self.checksum_public_address,
                                self.rest_server.rest_interface.host,
                                self.rest_server.rest_interface.port)

    @classmethod
    def from_tls_hosting_power(cls, tls_hosting_power: TLSHostingPower, *args, **kwargs) -> 'VerifiableNode':
        certificate_filepath = tls_hosting_power.keypair.certificate_filepath
        certificate = tls_hosting_power.keypair.certificate
        return cls(certificate=certificate, certificate_filepath=certificate_filepath, *args, **kwargs)

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
            message = "This node can't be verified in this manner, " \
                      "but is OK to use in federated mode if you" \
                      " have reason to believe it is trustworthy."
            raise self.WrongMode(message)
        else:
            raise self.InvalidNode

    def interface_is_valid(self):
        """
        Checks that the interface info is valid for this node's canonical address.
        """
        interface_info_message = self._signable_interface_info_message()  # Contains canonical address.
        message = self.timestamp_bytes() + interface_info_message
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

    def verify_node(self,
                    network_middleware,
                    certificate_filepath: str = None,
                    accept_federated_only: bool = False,
                    force: bool = False
                    ) -> bool:
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
                                                       port=self.rest_information()[0].port,
                                                       certificate_filepath=certificate_filepath)
        if not response.status_code == 200:
            raise RuntimeError("Or something.")  # TODO: Raise an error here?  Or return False?  Or something?
        timestamp, signature, identity_evidence, \
        verifying_key, encrypting_key, \
        public_address, certificate_vbytes, rest_info = self._internal_splitter(response.content)

        verifying_keys_match = verifying_key == self.public_keys(SigningPower)
        encrypting_keys_match = encrypting_key == self.public_keys(EncryptingPower)
        addresses_match = public_address == self.canonical_public_address
        evidence_matches = identity_evidence == self._evidence_of_decentralized_identity

        if not all((encrypting_keys_match, verifying_keys_match, addresses_match, evidence_matches)):
            # TODO: Optional reporting.  355
            if not addresses_match:
                self.log.warn("Wallet address swapped out.  It appears that someone is trying to defraud this node.")
            if not verifying_keys_match:
                self.log.warn("Verifying key swapped out.  It appears that someone is impersonating this node.")
            raise self.InvalidNode("Wrong cryptographic material for this node - something fishy going on.")
        else:
            self._verified_node = True

    def substantiate_stamp(self, passphrase: str):
        blockchain_power = self._crypto_power.power_ups(BlockchainPower)
        blockchain_power.unlock_account(password=passphrase)  # TODO: 349
        signature = blockchain_power.sign_message(bytes(self.stamp))
        self._evidence_of_decentralized_identity = signature

    def _signable_interface_info_message(self):
        message = self.canonical_public_address + self.rest_information()[0]
        return message

    def _sign_and_date_interface_info(self):
        message = self._signable_interface_info_message()
        self._timestamp = maya.now()
        self._interface_signature_object = self.stamp(self.timestamp_bytes() + message)

    @property
    def _interface_signature(self):
        if not self._interface_signature_object:
            try:
                self._sign_and_date_interface_info()
            except NoSigningPower:
                raise NoSigningPower("This Ursula is a stranger and cannot be used to verify.")
        return self._interface_signature_object

    @property
    def timestamp(self):
        if not self._timestamp:
            try:
                self._sign_and_date_interface_info()
            except NoSigningPower:
                raise NoSigningPower("This Node is a Stranger; you didn't init with a timestamp, so you can't verify.")
        return self._timestamp

    def timestamp_bytes(self):
        return self.timestamp.epoch.to_bytes(4, 'big')

    @property
    def common_name(self):
        x509 = OpenSSL.crypto.X509.from_cryptography(self.certificate)
        subject_components = x509.get_subject().get_components()
        common_name_as_bytes = subject_components[0][1]
        common_name_from_cert = common_name_as_bytes.decode()
        return common_name_from_cert

    @property
    def certificate_filename(self):
        return '{}.{}'.format(self.checksum_public_address, Encoding.PEM.name.lower())  # TODO: use cert's encoding..?

    def get_certificate_filepath(self, certificates_dir: str) -> str:
        return os.path.join(certificates_dir, self.certificate_filename)

    def save_certificate_to_disk(self, directory, force=False):
        x509 = OpenSSL.crypto.X509.from_cryptography(self.certificate)
        subject_components = x509.get_subject().get_components()
        common_name_as_bytes = subject_components[0][1]
        common_name_from_cert = common_name_as_bytes.decode()

        if not self.rest_information()[0].host == common_name_from_cert:
            # TODO: It's better for us to have checked this a while ago so that this situation is impossible.  #443
            raise ValueError("You passed a common_name that is not the same one as the cert. "
                             "Common name is optional; the cert will be saved according to "
                             "the name on the cert itself.")

        certificate_filepath = self.get_certificate_filepath(certificates_dir=directory)
        _write_tls_certificate(self.certificate, full_filepath=certificate_filepath, force=force)
        self.certificate_filepath = certificate_filepath
        self.log.info("Saved new TLS certificate {}".format(certificate_filepath))

    @classmethod
    def from_seednode_metadata(cls,
                               seednode_metadata,
                               *args,
                               **kwargs):
        """
        Essentially another deserialization method, but this one doesn't reconstruct a complete
        node from bytes; instead it's just enough to connect to and verify a node.
        """

        return cls.from_seed_and_stake_info(checksum_address=seednode_metadata.checksum_address,
                                            host=seednode_metadata.rest_host,
                                            port=seednode_metadata.rest_port,
                                            *args, **kwargs)

    @classmethod
    def from_seed_and_stake_info(cls, host,
                                 certificates_directory,
                                 federated_only,
                                 port=9151,
                                 checksum_address=None,
                                 timeout=2,
                                 minimum_stake=0,
                                 network_middleware=None,
                                 *args,
                                 **kwargs
                                 ):
        if network_middleware is None:
            network_middleware = RestMiddleware()

        certificate = network_middleware.get_certificate(host=host,
                                                         port=port,
                                                         )
        real_host = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        # Write certificate; this is really only for temporary purposes.  Ideally, we'd use
        # it in-memory here but there's no obvious way to do that.
        filename = '{}.{}'.format(checksum_address, Encoding.PEM.name.lower())
        certificate_filepath = os.path.join(certificates_directory, filename)
        _write_tls_certificate(certificate=certificate, full_filepath=certificate_filepath, force=True)
        cls.log.info("Saved seednode {} TLS certificate".format(checksum_address))

        potential_seed_node = cls.from_rest_url(
            host=real_host,
            port=port,
            network_middleware=network_middleware,
            certificate_filepath=certificate_filepath,
            federated_only=True,
            *args,
            **kwargs)  # TODO: 466

        if checksum_address:
            if not checksum_address == potential_seed_node.checksum_public_address:
                raise potential_seed_node.SuspiciousActivity(
                    "This seed node has a different wallet address: {} (was hoping for {}).  Are you sure this is a seed node?".format(
                        potential_seed_node.checksum_public_address,
                        checksum_address))
        else:
            if minimum_stake > 0:
                # TODO: check the blockchain to verify that address has more then minimum_stake. #511
                raise NotImplementedError("Stake checking is not implemented yet.")
        try:
            potential_seed_node.verify_node(
                network_middleware=network_middleware,
                accept_federated_only=federated_only,
                certificate_filepath=certificate_filepath)
        except potential_seed_node.InvalidNode:
            raise  # TODO: What if our seed node fails verification?
        return potential_seed_node

    @classmethod
    def from_rest_url(cls,
                      network_middleware: RestMiddleware,
                      host: str,
                      port: int,
                      certificate_filepath,
                      federated_only: bool = False,
                      *args,
                      **kwargs):

        response = network_middleware.node_information(host, port, certificate_filepath=certificate_filepath)
        if not response.status_code == 200:
            raise RuntimeError("Got a bad response: {}".format(response))

        stranger_ursula_from_public_keys = cls.from_bytes(response.content, federated_only=federated_only)
        return stranger_ursula_from_public_keys

    def nickname_icon(self):
        icon_template = """
        <div class="nucypher-nickname-icon" style="border-top-color:{first_color}; border-left-color:{first_color}; border-bottom-color:{second_color}; border-right-color:{second_color};">
        <span class="symbol" style="color: {first_color}">{first_symbol}</span>
        <span class="symbol" style="color: {second_color}">{second_symbol}</span>
        <br/>
        <span class="small-address">{address_first6}</span>
        </div>
        """.replace("  ", "").replace('\n', "")
        return icon_template.format(
            first_color=self.nickname_metadata[0]['hex'],
            first_symbol=self.nickname_metadata[1],
            second_color=self.nickname_metadata[2]['hex'],
            second_symbol=self.nickname_metadata[3],
            address_first6=self.checksum_public_address[2:8]
        )
