from typing import Callable

from cryptography.fernet import Fernet
from nucypher_core import AccessControlPolicy, Conditions, ThresholdMessageKit
from nucypher_core.ferveo import (
    DkgPublicKey,
    encrypt,
)

from nucypher.crypto.utils import keccak_digest


def _validate_aad_compatibility(tmk_aad: bytes, acp_aad: bytes):
    if tmk_aad != acp_aad:
        raise ValueError("Incompatible ThresholdMessageKit and AccessControlPolicy")


def encrypt_data(
        plaintext: bytes,
        conditions: Conditions,
        dkg_public_key: DkgPublicKey,
        signer: Callable[[bytes], bytes],
) -> ThresholdMessageKit:
    symmetric_key = Fernet.generate_key()
    fernet = Fernet(symmetric_key)
    payload = fernet.encrypt(plaintext)

    aad = bytes(dkg_public_key) + str(conditions).encode()
    header = encrypt(symmetric_key, aad, dkg_public_key)

    header_hash = keccak_digest(bytes(header))
    authorization = signer(header_hash)

    acp = AccessControlPolicy(
        public_key=dkg_public_key,
        conditions=conditions,
        authorization=authorization,
    )

    # we need to link the ThresholdMessageKit to a specific version of the ACP
    # because the ACP.aad() function should return the same value as the aad used
    # for encryption. Since the ACP version can change independently of
    # ThresholdMessageKit this check is good for code maintenance and ensuring
    # compatibility - unless we find a better way to link TMK and ACP.
    #
    # TODO: perhaps this can be improved. You could have ACP be an inner class of TMK,
    #  but not sure how that plays out with rust and python bindings... OR ...?
    _validate_aad_compatibility(aad, acp.aad())

    return ThresholdMessageKit(
        header=header,
        payload=payload,
        acp=acp,
    )
