from cryptography.hazmat.primitives import hashes
from constant_sorrow import constants

BLAKE2B = hashes.BLAKE2b(64)

BLAKE2B_DIGEST_LENGTH = 64
KECCAK_DIGEST_LENGTH = 32

UNKNOWN_KFRAG = 404


NO_DECRYPTION_PERFORMED = 455

# These lengths are specific to secp256k1
KFRAG_LENGTH = 194
CFRAG_LENGTH = 131
CAPSULE_LENGTH = 98
PUBLIC_KEY_LENGTH = 33
