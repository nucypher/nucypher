from pathlib import Path

from a_few_conditions import ten_oclock_florida_time
from awful_things_done_in_the_name_of_making_the_demo_work import Crony
from ferveo_py.ferveo_py import DkgPublicKey
from nucypher_core import ferveo

import nucypher
from examples.tdec.discord.awful_things_done_in_the_name_of_making_the_demo_work import (
    BobGonnaBob,
    NiceGuyEddie,
)
from examples.tdec.discord.ferveo_example_also import dkg
from nucypher.blockchain.eth.registry import LocalContractRegistry
from nucypher.characters.lawful import Enrico
from nucypher.crypto.powers import DecryptingPower

# parser = argparse.ArgumentParser(
#     prog='The Enrico Part of Threshold CBD for Discord bots and similar machinery',
#     description='Encrypts <plaintext_filename>',
#     epilog='Publish the world!')
#
# parser.add_argument('plaintext_filename')
# parser.add_argument('-o', '--output_filename')
# args = parser.parse_args()


##################
# Enrico
###################


def get_ritualistic_enrico(ritual_id=None, trinket=None):
    network = "mumbai"
    nucypher_package_dir = Path(nucypher.__file__).parent
    here = Path(__file__).parent
    registry_filepath = (
        nucypher_package_dir
        / f"blockchain/eth/contract_registry/{network}/contract_registry.json"
    )
    registry = LocalContractRegistry(filepath=registry_filepath)

    # with open(here / args.plaintext_filename, "rb") as f:
    #     plaintext = f.read()

    if ritual_id:
        # coordinator_agent = CoordinatorAgent(eth_provider_uri=INFURA_ENDPOINT, registry=registry)
        # ritual_id = 0  # got this from a side channel
        # ritual = coordinator_agent.get_ritual(ritual_id)
        enrico = Enrico(encrypting_key=DkgPublicKey.from_bytes(ritual.public_key))
    elif trinket:
        enrico = Enrico(encrypting_key=trinket)
    else:
        raise ValueError("Need either a trinket or a ritual ID.")

    return enrico


decryptor_crony = Crony(domain="lynx")
# plaintext_filename = args.plaintext_filename

# with open(nucypher_package_dir /)

# crony_trinket = decryptor_crony.public_keys(DecryptingPower)


plaintext = b"PEACE AD DAWN"
I_CHOOSE_NOT_TO_RITUAL = 500

# cipher\text, tdr = enrico.encrypt_for_dkg_and_produce_decryption_request(
#     plaintext=plaintext,
#     conditions=[ten_oclock_florida_time, ],
#     variant_id=0,
#     ritual_id=I_CHOOSE_NOT_TO_RITUAL,
# )

# print(ciphertext)

# Essentiall curtains here, but let's go a little further into Bob.


def gen_eth_addr(i: int) -> str:
    return f"0x{i:040x}"


tau = 1
security_threshold = 3
shares_num = 4

### Here is the generation thing.
validator_keypairs = [ferveo.Keypair.random() for _ in range(0, shares_num)]

crony = Crony()

validators = [
    ferveo.Validator(gen_eth_addr(i), keypair.public_key())
    for i, keypair in enumerate(validator_keypairs)
]

# Validators must be sorted by their public key
validators.sort(key=lambda v: v.address)

# Each validator holds their own DKG instance and generates a transcript every
# validator, including themselves
messages = []
for sender in validators:
    dkg = ferveo.Dkg(
        tau=tau,
        shares_num=shares_num,
        security_threshold=security_threshold,
        validators=validators,
        me=sender,
    )
    messages.append((sender, dkg.generate_transcript()))

# Now that every validator holds a dkg instance and a transcript for every other validator,
# every validator can aggregate the transcripts
me = validators[0]
dkg = ferveo.Dkg(
    tau=tau,
    shares_num=shares_num,
    security_threshold=security_threshold,
    validators=validators,
    me=me,
)

enrico = NiceGuyEddie(encrypting_key=dkg.public_key, dkg=dkg)

# Server can aggregate the transcripts
server_aggregate = dkg.aggregate_transcripts(messages)
assert server_aggregate.verify(shares_num, messages)

# And the client can also aggregate and verify the transcripts
client_aggregate = ferveo.AggregatedTranscript(messages)
assert client_aggregate.verify(shares_num, messages)

# In the meantime, the client creates a ciphertext and decryption request
msg = "abc".encode()
aad = "my-aad".encode()
ciphertext = ferveo.encrypt(msg, aad, dkg.public_key)


# The client can serialize/deserialize ciphertext for transport
ciphertext_ser = bytes(ciphertext)

# Having aggregated the transcripts, the validators can now create decryption shares
decryption_shares = []
for validator, validator_keypair in zip(validators, validator_keypairs):
    dkg = ferveo.Dkg(
        tau=tau,
        shares_num=shares_num,
        security_threshold=security_threshold,
        validators=validators,
        me=validator,
    )

    # We can also obtain the aggregated transcript from the side-channel (deserialize)
    aggregate = ferveo.AggregatedTranscript(messages)
    assert aggregate.verify(shares_num, messages)

    # The ciphertext is obtained from the client

    # Create a decryption share for the ciphertext
    decryption_share = aggregate.create_decryption_share_simple(
        dkg, ciphertext, aad, validator_keypair
    )
    decryption_shares.append(decryption_share)

# Now, the decryption share can be used to decrypt the ciphertext
# This part is in the client API

shared_secret = ferveo.combine_decryption_shares_simple(decryption_shares)

# The client should have access to the public parameters of the DKG

plaintext = ferveo.decrypt_with_shared_secret(
    ciphertext, aad, shared_secret, dkg.public_params
)
assert bytes(plaintext) == msg

bob = BobGonnaBob(domain="lynx")

bob.threshold_decrypt(ciphertext=ciphertext)
