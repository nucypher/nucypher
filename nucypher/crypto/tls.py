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
from ipaddress import IPv4Address
from pathlib import Path
from typing import ClassVar, Tuple

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.backends.openssl.ec import _EllipticCurvePrivateKey
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurve
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509 import Certificate
from cryptography.x509.oid import NameOID

from nucypher.crypto.umbral_adapter import SecretKey

_TLS_CERTIFICATE_ENCODING = Encoding.PEM
_TLS_CURVE = ec.SECP384R1


def _write_tls_certificate(certificate: Certificate,
                           full_filepath: Path,
                           force: bool = False,
                           ) -> Path:
    cert_already_exists = full_filepath.is_file()
    if force is False and cert_already_exists:
        raise FileExistsError('A TLS certificate already exists at {}.'.format(full_filepath.resolve()))

    with open(full_filepath, 'wb') as certificate_file:
        public_pem_bytes = certificate.public_bytes(_TLS_CERTIFICATE_ENCODING)
        certificate_file.write(public_pem_bytes)
    return full_filepath


def _read_tls_certificate(filepath: Path) -> Certificate:
    """Deserialize an X509 certificate from a filepath"""
    try:
        with open(filepath, 'rb') as certificate_file:
            cert = x509.load_pem_x509_certificate(certificate_file.read(), backend=default_backend())
            return cert
    except FileNotFoundError:
        raise FileNotFoundError("No SSL certificate found at {}".format(filepath))


def generate_self_signed_certificate(host: str,
                                     private_key: SecretKey = None,
                                     days_valid: int = 365,
                                     curve: ClassVar[EllipticCurve] = _TLS_CURVE,
                                     ) -> Tuple[Certificate, _EllipticCurvePrivateKey]:

    if private_key:
        private_bn = int.from_bytes(private_key.to_secret_bytes(), 'big')
        private_key = ec.derive_private_key(private_value=private_bn, curve=curve())
    else:
        private_key = ec.generate_private_key(curve(), default_backend())
    public_key = private_key.public_key()

    now = datetime.datetime.utcnow()
    fields = [x509.NameAttribute(NameOID.COMMON_NAME, host)]

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
