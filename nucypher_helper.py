import json
import os
import random
from umbral import pre
from umbral.kfrags import KFrag

KFRAGS_FILE = "ursula.kfrags"

def grant_access_policy(delgating_privkey, signer, receiving_pubkey, m, n):
    if os.path.exists(KFRAGS_FILE):
        os.remove(KFRAGS_FILE)

    kfrags = pre.generate_kfrags(delegating_privkey=delgating_privkey,
                                 signer=signer,
                                 receiving_pubkey=receiving_pubkey,
                                 threshold=m,
                                 N=n)

    kfrags = random.sample(kfrags, m)
    kfrag_hex_list = list()
    for kfrag in kfrags:
        kfrag_hex_list.append(kfrag.to_bytes().hex())

    with open(KFRAGS_FILE, 'w') as f:
        json.dump(kfrag_hex_list, f)

    print("Access Granted!")


def reencrypt_data(alice_pub_key, bob_pub_key, alice_verify_key, capsule):
    with open(KFRAGS_FILE) as f:
        stored_kfrags = json.load(f)

    kfrags = list()
    for kfrag_hex in stored_kfrags:
        kfrag = KFrag.from_bytes(bytes.fromhex(kfrag_hex))
        kfrags.append(kfrag)

    capsule.set_correctness_keys(delegating=alice_pub_key,
                                 receiving=bob_pub_key,
                                 verifying=alice_verify_key)

    for kfrag in kfrags:
        cfrag = pre.reencrypt(kfrag=kfrag, capsule=capsule)
        capsule.attach_cfrag(cfrag)
