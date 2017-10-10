import msgpack
import sha3
from random import SystemRandom
from npre import umbral
from npre import elliptic_curve
from nacl.secret import SecretBox
from typing import Tuple, Union, List
from py_ecc.secp256k1 import ecdsa_raw_recover, ecdsa_raw_sign


PRE = umbral.PRE()
SYSTEM_RAND = SystemRandom()


def secure_random(
    num_bytes: int
) -> bytes:
    """
    Returns an amount `num_bytes` of data from the OS's random device.
    If a randomness source isn't found, returns a `NotImplementedError`.
    In this case, a secure random source most likely doesn't exist and
    randomness will have to found elsewhere.

    :param num_bytes: Number of bytes to return.

    :return: bytes
    """
    # TODO: Should we just use os.urandom or avoid the import w/ this?
    return SYSTEM_RAND.getrandbits(num_bytes*8).to_bytes(num_bytes,
                                                         byteorder='big')


def secure_random_range(
    min: int,
    max: int
) -> int:
    """
    Returns a number from a secure random source betwee the range of
    `min` and `max` - 1.

    :param min: Minimum number in the range
    :param max: Maximum number in the range

    :return: int
    """
    return SYSTEM_RAND.randrange(min, max)


def vrs_msgpack_dump(v, r, s):
    v_bytes = v.to_bytes(1, byteorder='big')
    r_bytes = r.to_bytes(32, byteorder='big')
    s_bytes = s.to_bytes(32, byteorder='big')
    return msgpack.dumps((v_bytes, r_bytes, s_bytes))


def vrs_msgpack_load(msgpack_vrs):
    sig = msgpack.loads(msgpack_vrs)
    v = int.from_bytes(sig[0], byteorder='big')
    r = int.from_bytes(sig[1], byteorder='big')
    s = int.from_bytes(sig[2], byteorder='big')
    return (v, r, s)


def keccak_digest(*messages):
    """
    Accepts an iterable containing bytes and digests it returning a
    Keccak digest of 32 bytes (keccak_256).

    :param bytes *messages: Data to hash

    :rtype: bytes
    :return: bytestring of digested data
    """
    hash = sha3.keccak_256()
    for message in messages:
        hash.update(message)
    return hash.digest()


def verify(signature, msghash, pubkey=None):
    """
    Takes a msgpacked signature and verifies the message.

    :param bytes msghash: The hashed message to verify
    :param bytes signature: The msgpacked signature (v, r, and s)
    :param bytes pubkey: Pubkey to validate signature for
                         Default is the keypair's pub_key.

    :rtype: Boolean
    :return: Is the signature valid or not?
    """
    sig = vrs_msgpack_load(signature)
    # Generate the public key from the signature and validate
    # TODO: Look into fixed processing time functions for comparison
    verify_sig = ecdsa_raw_recover(msghash, sig)
    return verify_sig == pubkey


def symm_encrypt(
        key: bytes,
        plaintext: bytes
) -> bytes:
    """
    Performs symmetric encryption using nacl.SecretBox.

    :param key: Key to encrypt with
    :param plaintext: Plaintext to encrypt

    :return: Encrypted ciphertext
    """
    cipher = SecretBox(key)
    return cipher.encrypt(plaintext)


def symm_decrypt(
        key: bytes,
        ciphertext: bytes
) -> bytes:
    """
    Decrypts ciphertext performed with nacl.SecretBox.

    :param key: Key to decrypt with
    :param ciphertext: Nacl.SecretBox ciphertext to decrypt

    :return: Decrypted Plaintext
    """
    cipher = SecretBox(key)
    return cipher.decrypt(ciphertext)


def priv_bytes2ec(
        privkey: bytes
) -> elliptic_curve.ec_element:
    """
    Turns a private key, in bytes, into an elliptic_curve.ec_element.

    :param privkey: Private key to turn into an elliptic_curve.ec_element.

    :return: elliptic_curve.ec_element
    """
    return elliptic_curve.deserialize(PRE.ecgroup, b'\x00' + privkey)


def pub_bytes2ec(
        pubkey: bytes,
) -> elliptic_curve.ec_element:
    """
    Turns a public key, in bytes, into an elliptic_curve.ec_element.

    :param pubkey: Public key to turn into an elliptic_curve.ec_element.

    :return: elliptic_curve.ec_element
    """
    return elliptic_curve.deserialize(PRE.ecgroup, b'\x01' + pubkey)


def ecies_gen_priv(
        to_bytes: bool = True
) -> Union[bytes, elliptic_curve.ec_element]:
    """
    Generates an ECIES private key.

    :param to_bytes: Return the byte serialization of the privkey?

    :return: An ECIES private key
    """
    privkey = PRE.gen_priv()
    if to_bytes:
        return elliptic_curve.serialize(privkey)[1:]
    return privkey


def ecies_priv2pub(
        privkey: Union[bytes, elliptic_curve.ec_element],
        to_bytes: bool = True
) -> Union[bytes, elliptic_curve.ec_element]:
    """
    Takes a private key (secret bytes or an elliptic_curve.ec_element) and
    derives the Public key from it.

    :param privkey: The Private key to derive the public key from
    :param to_bytes: Return the byte serialization of the pubkey?

    :return: The Public component of the Private key provided
    """
    if type(privkey) == bytes:
        privkey = priv_bytes2ec(privkey)

    pubkey = PRE.priv2pub(privkey)
    if to_bytes:
        return elliptic_curve.serialize(pubkey)[1:]
    return pubkey


def ecies_encapsulate(
        pubkey: Union[bytes, elliptic_curve.ec_element],
) -> Tuple[bytes, umbral.EncryptedKey]:
    """
    Encapsulates an ECIES generated symmetric key for a public key.

    :param pubkey: Pubkey to generate a key for

    :return: Generated key in bytes, and EncryptedKey
    """
    if type(pubkey) == bytes:
        pubkey = pub_bytes2ec(pubkey)
    return PRE.encapsulate(pubkey)


def ecies_decapsulate(
        privkey: Union[bytes, elliptic_curve.ec_element],
        enc_key: umbral.EncryptedKey
) -> bytes:
    """
    Decapsulates an ECIES generated encrypted key with a private key.

    :param privkey: Private key to decrypt the key with
    :param enc_key: Encrypted Key to decrypt

    :return: Decrypted symmetric key
    """
    if type(privkey) == bytes:
        privkey = priv_bytes2ec(privkey)
    return PRE.decapsulate(privkey, enc_key)


def ecies_rekey(
        privkey_a: Union[bytes, elliptic_curve.ec_element],
        privkey_b: Union[bytes, elliptic_curve.ec_element],
        to_bytes: bool = True
) -> Union[bytes, umbral.RekeyFrag]:
    """
    Generates a re-encryption key from privkey_a to privkey_b.

    :param privkey_a: Private key to re-encrypt from
    :param privkey_b: Private key to re-encrypt to
    :param to_bytes: Format result as bytes?

    :return: Re-encryption key
    """
    if type(privkey_a) == bytes:
        privkey_a = priv_bytes2ec(privkey_a)
    if type(privkey_b) == bytes:
        privkey_b = priv_bytes2ec(privkey_b)

    rk = PRE.rekey(privkey_a, privkey_b)
    if to_bytes:
        return elliptic_curve.serialize(rk.key)[1:]
    return rk


def ecies_split_rekey(
        privkey_a: Union[bytes, elliptic_curve.ec_element],
        privkey_b: Union[bytes, elliptic_curve.ec_element],
        min_shares: int,
        total_shares: int
) -> List[umbral.RekeyFrag]:
    """
    Performs a split-key re-encryption key generation where a minimum
    number of shares `min_shares` are required to reproduce a rekey.
    Will split a rekey into `total_shares`.

    :param privkey_a: Privkey to re-encrypt from
    :param privkey_b: Privkey to re-encrypt to
    :param min_shares: Minimum shares needed to reproduce rekey
    :param total_shares: Total shares to generate from split-rekey gen

    :return: A list of RekeyFrags to distribute
    """
    if type(privkey_a) == bytes:
        privkey_a = priv_bytes2ec(privkey_a)
    if type(privkey_b) == bytes:
        privkey_b = priv_bytes2ec(privkey_b)
    return PRE.split_rekey(privkey_a, privkey_b,
                           min_shares, total_shares)


def ecies_combine(
        encrypted_keys: List[umbral.EncryptedKey]
) -> umbral.EncryptedKey:
    """
    Combines the encrypted keys together to form a rekey from split_rekey.

    :param encrypted_keys: Encrypted keys to combine

    :return: The combined EncryptedKey of the rekey
    """
    return PRE.combine(encrypted_keys)


def ecies_reencrypt(
        rekey: Union[bytes, umbral.RekeyFrag],
        enc_key: Union[bytes, umbral.EncryptedKey],
) -> umbral.EncryptedKey:
    """
    Re-encrypts the key provided.

    :param rekey: Re-encryption key to use
    :param enc_key: Encrypted key to re-encrypt

    :return: The re-encrypted key
    """
    if type(rekey) == bytes:
        rekey = umbral.RekeyFrag(None, priv_bytes2ec(rekey))
    if type(enc_key) == bytes:
        enc_key = umbral.EncryptedKey(priv_bytes2ec(enc_key), None)
    return PRE.reencrypt(rekey, enc_key)
