from py_ecc.secp256k1 import N, privtopub

from nkms.crypto.api import SYSTEM_RAND


def generate_random_keypair():
    priv_number = SYSTEM_RAND.randrange(1, N)
    priv_key = priv_number.to_bytes(32, byteorder='big')
    # Get the public component
    pub_key = privtopub(priv_key)
    return priv_key, pub_key


def pubkey_tuple_to_bytes(pub_key):
    return b''.join(i.to_bytes(32, 'big') for i in pub_key)