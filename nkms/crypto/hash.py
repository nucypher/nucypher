import random

# TODO: Replace these with actual hash functions.

def signature_hash(hash_input):
    return random.getrandbits(128)


def content_hash(hash_input):
    return random.getrandbits(128)