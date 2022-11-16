


from cryptography.hazmat.primitives import hashes

# Policy component sizes
SIGNATURE_SIZE = 64

# Digest Lengths
KECCAK_DIGEST_LENGTH = 32
BLAKE2B_DIGEST_LENGTH = 64

# Hashes
SHA256 = hashes.SHA256()
BLAKE2B = hashes.BLAKE2b(64)
