from nkms.crypto import api as API
from typing import Tuple, Union
from npre import elliptic_curve


def _ecies_gen_ephemeral_key(
        recp_pubkey: Union[bytes, elliptic_curve.ec_element]
) -> Tuple[bytes, bytes]:
    """
    Generates and encrypts an ephemeral key for the `recp_pubkey`.

    :param recp_pubkey: Recipient's pubkey

    :return: Tuple of encrypted symmetric key, and encrypted ephemeral privkey
    """
    pass
