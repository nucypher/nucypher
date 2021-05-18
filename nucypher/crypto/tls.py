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

import datetime
import os
from ipaddress import IPv4Address
from typing import Tuple

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.backends.openssl.ec import _EllipticCurvePrivateKey
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurve
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509 import Certificate
from cryptography.x509.oid import NameOID
from eth_utils.address import is_checksum_address

from nucypher.crypto.utils import InvalidNodeCertificate

_TLS_CERTIFICATE_ENCODING = Encoding.PEM
_TLS_CURVE = ec.SECP256R1


def read_certificate_pseudonym(certificate: Certificate):
    """Return the checksum address written into a TLS certificates pseudonym field or raise an error."""
    try:
        pseudonym = certificate.subject.get_attributes_for_oid(NameOID.PSEUDONYM)[0]
    except IndexError:
        raise InvalidNodeCertificate("Invalid teacher certificate encountered: No checksum address present as pseudonym.")
    checksum_address = pseudonym.value
    if not is_checksum_address(checksum_address):
        raise InvalidNodeCertificate("Invalid certificate checksum address encountered")
    return checksum_address


def _write_tls_certificate(certificate: Certificate,
                           full_filepath: str,
                           force: bool = False,
                           ) -> str:
    cert_already_exists = os.path.isfile(full_filepath)
    if force is False and cert_already_exists:
        raise FileExistsError('A TLS certificate already exists at {}.'.format(full_filepath))

    with open(full_filepath, 'wb') as certificate_file:
        public_pem_bytes = certificate.public_bytes(__TLS_CERTIFICATE_ENCODING)
        certificate_file.write(public_pem_bytes)
    return full_filepath


def _read_tls_certificate(filepath: str) -> Certificate:
    """Deserialize an X509 certificate from a filepath"""
    try:
        with open(filepath, 'rb') as certificate_file:
            cert = x509.load_pem_x509_certificate(certificate_file.read(), backend=default_backend())
            return cert
    except FileNotFoundError:
        raise FileNotFoundError("No SSL certificate found at {}".format(filepath))


def _generate_tls_keys(host: str, checksum_address: str, curve: EllipticCurve) -> Tuple[_EllipticCurvePrivateKey, Certificate]:
    cert, private_key = generate_teacher_certificate(host=host, curve=curve, checksum_address=checksum_address)
    return private_key, cert


def _serialize_private_key_to_pem(key_data, password: bytes) -> bytes:
    return key_data.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.BestAvailableEncryption(password=password)
    )


def __generate_self_signed_certificate(host: str,
                                       curve: EllipticCurve = _TLS_CURVE,
                                       private_key: _EllipticCurvePrivateKey = None,
                                       days_valid: int = 365,
                                       checksum_address: str = None
                                       ) -> Tuple[Certificate, _EllipticCurvePrivateKey]:

    if not private_key:
        private_key = ec.generate_private_key(curve, default_backend())
    public_key = private_key.public_key()

    now = datetime.datetime.utcnow()
    fields = [
        x509.NameAttribute(NameOID.COMMON_NAME, host),
    ]
    if checksum_address:
        # Teacher Certificate
        pseudonym = x509.NameAttribute(NameOID.PSEUDONYM, checksum_address)
        fields.append(pseudonym)

    subject = issuer = x509.Name(fields)
    cert = x509.CertificateBuilder().subject_name(subject)
    cert = cert.issuer_name(issuer)
    cert = cert.public_key(public_key)
    cert = cert.serial_number(x509.random_serial_number())
    cert = cert.not_valid_before(now)
    cert = cert.not_valid_after(now + datetime.timedelta(days=days_valid))
    cert = cert.add_extension(x509.SubjectAlternativeName([x509.IPAddress(IPv4Address(host))]), critical=False)
    cert = cert.sign(private_key, hashes.SHA512(), default_backend())

    return cert, private_key


def generate_teacher_certificate(checksum_address: str, *args, **kwargs):
    cert = __generate_self_signed_certificate(checksum_address=checksum_address, *args, **kwargs)
    return cert


def generate_self_signed_certificate(*args, **kwargs):
    if 'checksum_address' in kwargs:
        raise ValueError("checksum address cannot be used to generate standard self-signed certificates.")
    cert = __generate_self_signed_certificate(checksum_address=None, *args, **kwargs)
    return cert
