import sha3
from random import SystemRandom
from npre import umbral
from npre import elliptic_curve
from nacl.secret import SecretBox
from typing import Tuple, Union, List
from py_ecc.secp256k1 import N, privtopub, ecdsa_raw_recover, ecdsa_raw_sign


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


def keccak_digest(
    *messages: bytes
) -> bytes:
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


def ecdsa_pub2bytes(
    pubkey: Tuple[int]
) -> bytes:
    """
    Takes an ECDSA public key and converts to bytes.

    :param pubkey: Tuple[int] of Public Key

    :return: bytestring of Public key
    """
    x = pubkey[0].to_bytes(32, byteorder='big')
    y = pubkey[1].to_bytes(32, byteorder='big')
    return x+y


def ecdsa_bytes2pub(
    pubkey: bytes
) -> Tuple[int]:
    """
    Takes a byte encoded ECDSA public key and converts to a Tuple of x, and y

    :param pubkey: Byte encoded public key

    :return: Tuple[int] of Public Key
    """
    x = int.from_bytes(pubkey[:32], byteorder='big')
    y = int.from_bytes(pubkey[32:], byteorder='big')
    return (x, y)


def ecdsa_gen_priv() -> bytes:
    """
    Generates an ECDSA Private Key.

    :return: Byte encoded ECDSA privkey
    """
    privkey = secure_random_range(1, N)
    return privkey.to_bytes(32, byteorder='big')


def ecdsa_priv2pub(
    privkey: bytes,
    to_bytes: bool = True
) -> Union[bytes, Tuple[int]]:
    """
    Returns the public component of an ECDSA private key.

    :param privkey: Private key as an int or bytestring
    :param to_bytes: Serialize to bytes or not?

    :return: Byte encoded or Tuple[int] ECDSA pubkey
    """
    pubkey = privtopub(privkey)
    if to_bytes:
        return ecdsa_pub2bytes(pubkey)
    return pubkey


def ecdsa_gen_sig(
    v: int,
    r: int,
    s: int
) -> bytes:
    """
    Generates an ECDSA signature, in bytes.

    :param v: v of sig
    :param r: r of sig
    :param s: s of sig

    :return: bytestring of v, r, and s
    """
    v = v.to_bytes(1, byteorder='big')
    r = r.to_bytes(32, byteorder='big')
    s = s.to_bytes(32, byteorder='big')
    return v+r+s


def ecdsa_load_sig(
    signature: bytes
) -> Tuple[int]:
    """
    Loads an ECDSA signature, from a bytestring, to a tuple.

    :param signature: Signature, as a bytestring, of v, r, and s.

    :return: Tuple(v, r, s)
    """
    v = int.from_bytes(signature[:1], byteorder='big')
    r = int.from_bytes(signature[1:33], byteorder='big')
    s = int.from_bytes(signature[33:], byteorder='big')
    return (v, r, s)


def ecdsa_sign(
    msghash: bytes,
    privkey: bytes
) -> Tuple[int]:
    """
    Accepts a hashed message and signs it with the private key given.

    :param msghash: Hashed message to sign
    :param privkey: Private key to sign with

    :return: Tuple(v, r, s)
    """
    v, r, s = ecdsa_raw_sign(msghash, privkey)
    return (v, r, s)


def ecdsa_verify(
    v: int,
    r: int,
    s: int,
    msghash: bytes,
    pubkey: Union[bytes, Tuple[int]]
) -> bool:
    """
    Takes a v, r, s, a pubkey, and a hash of a message to verify via ECDSA.

    :param v: V of sig
    :param r: R of sig
    :param s: S of sig
    :param bytes msghash: The hashed message to verify
    :param bytes pubkey: Pubkey to validate signature for

    :rtype: Boolean
    :return: Is the signature valid or not?
    """
    if bytes == type(pubkey):
        pubkey = ecdsa_bytes2pub(pubkey)

    verify_sig = ecdsa_raw_recover(msghash, (v, r, s))
    # TODO: Should this equality test be done better?
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


def generate_random_keypair():
    priv_number = SYSTEM_RAND.randrange(1, N)
    priv_key = priv_number.to_bytes(32, byteorder='big')
    # Get the public component
    pub_key = privtopub(priv_key)
    return priv_key, pub_key


def pubkey_tuple_to_bytes(pub_key):
    return b''.join(i.to_bytes(32, 'big') for i in pub_key)