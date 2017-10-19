from nkms.crypto import api as API
from typing import Tuple, Union
from npre import elliptic_curve


def _ecies_gen_ephemeral_key(
        recp_pubkey: Union[bytes, elliptic_curve.ec_element]
) -> Tuple[bytes, Tuple[bytes, bytes]]:
    """
    Generates and encrypts an ephemeral key for the `recp_pubkey`.

    :param recp_pubkey: Recipient's pubkey

    :return: Tuple of the eph_privkey, and a tuple of the encrypted symmetric
             key, and encrypted ephemeral privkey
    """
    symm_key, enc_symm_key = API.ecies_encapsulate(recp_pubkey)
    eph_privkey = API.ecies_gen_priv()

    enc_eph_privkey = API.symm_encrypt(symm_key, eph_privkey)
    return (eph_privkey, (enc_symm_key, enc_eph_privkey))
