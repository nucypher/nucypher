# This is not an actual mining script.  Don't use this to mine - you won't
# perform any re-encryptions, and you won't get paid.
# It might be (but might not be) useful for determining whether you have
# the proper depedencies and configuration to run an actual mining node.

# WIP w/ hendrix@tags/3.3.0rc1

import os

from cryptography.hazmat.primitives.asymmetric import ec

from hendrix.deploy.tls import HendrixDeployTLS
from hendrix.facilities.services import ExistingKeyTLSContextFactory
from nkms.characters import Ursula
from OpenSSL.crypto import X509
from OpenSSL.SSL import TLSv1_2_METHOD

from nkms.crypto.api import generate_self_signed_certificate

DB_NAME = "non-mining-proxy-node"

_URSULA = Ursula(dht_port=3501, rest_port=3601, ip_address="localhost", db_name=DB_NAME)
_URSULA.dht_listen()

CURVE = ec.SECP256R1
cert, private_key = generate_self_signed_certificate(_URSULA.stamp.fingerprint().decode(), CURVE)

deployer = HendrixDeployTLS("start",
                            {"wsgi":_URSULA.rest_app, "https_port": _URSULA.rest_port},
                            key=private_key,
                            cert=X509.from_cryptography(cert),
                            context_factory=ExistingKeyTLSContextFactory,
                            context_factory_kwargs={"curve_name": "prime256v1",
                                                    "sslmethod": TLSv1_2_METHOD})

try:
    deployer.run()
finally:
    os.remove(DB_NAME)
