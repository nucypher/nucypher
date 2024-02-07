import datetime
from ipaddress import IPv4Address
from pathlib import Path
from typing import Optional, Tuple, Type

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import (
    EllipticCurve,
    EllipticCurvePrivateKey,
)
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509 import Certificate
from cryptography.x509.oid import NameOID

_TLS_CERTIFICATE_ENCODING = Encoding.PEM
_TLS_CURVE = ec.SECP384R1


def _read_tls_certificate(filepath: Path) -> Certificate:
    """Deserialize an X509 certificate from a filepath"""
    try:
        with open(filepath, 'rb') as certificate_file:
            cert = x509.load_der_x509_certificate(certificate_file.read(), backend=default_backend())
            return cert
    except FileNotFoundError:
        raise FileNotFoundError("No SSL certificate found at {}".format(filepath))


def generate_self_signed_certificate(
    host: str,
    secret_seed: Optional[bytes] = None,
    days_valid: int = 365,
    curve: Type[EllipticCurve] = _TLS_CURVE,
) -> Tuple[Certificate, EllipticCurvePrivateKey]:
    if secret_seed:
        private_bn = int.from_bytes(secret_seed[: _TLS_CURVE.key_size // 8], "big")
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
