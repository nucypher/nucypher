import json
import os
import random
from umbral import pre
from umbral.kfrags import KFrag

KFRAGS_FOLDER = './kfrags'
KFRAGS_FILE_FORMAT = KFRAGS_FOLDER + '/ursula.{}.kfrags'


class AccessError(ValueError):
    pass


def grant_access_policy(delegating_privkey, signer, recipient_pubkey, m, n):
    kfrags_file = KFRAGS_FILE_FORMAT.format(recipient_pubkey.to_bytes().hex())
    if os.path.exists(kfrags_file):
        os.remove(kfrags_file)

    kfrags = pre.generate_kfrags(delegating_privkey=delegating_privkey,
                                 signer=signer,
                                 receiving_pubkey=recipient_pubkey,
                                 threshold=m,
                                 N=n)

    kfrags = random.sample(kfrags, m)
    kfrag_hex_list = list()
    for kfrag in kfrags:
        kfrag_hex_list.append(kfrag.to_bytes().hex())

    with open(kfrags_file, 'w') as f:
        json.dump(kfrag_hex_list, f)

    print("Access Granted!")


def reencrypt_data(alice_pub_key, bob_pub_key, alice_verify_key, capsule):
    kfrags_file = KFRAGS_FILE_FORMAT.format(bob_pub_key.to_bytes().hex())
    try:
        with open(kfrags_file) as f:
            stored_kfrags = json.load(f)
    except FileNotFoundError as e:
        raise AccessError('Access Denied')

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


def revoke_access(recipient_pubkey_hex):
    kfrags_file = KFRAGS_FILE_FORMAT.format(recipient_pubkey_hex)
    if os.path.exists(kfrags_file):
        os.remove(kfrags_file)
