import functools
import json
from collections.abc import Mapping

import maya

from nucypher.characters.control.specifications import alice, bob, enrico
from umbral.keys import UmbralPublicKey

from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import DecryptingPower, SigningPower
from nucypher.crypto.utils import construct_policy_id
from nucypher.network.middleware import NotFound


class CharacterPublicInterface:

    specification = NotImplemented

    def __init__(self, character=None, *args, **kwargs):
        self.character = character
        super().__init__(*args, **kwargs)


class AliceInterface(CharacterPublicInterface):

    specifications = {'create_policy': alice.CreatePolicy(),
                      'derive_policy_encrypting_key': alice.DerivePolicyEncryptionKey(),
                      'grant': alice.GrantPolicy(),
                      'revoke': alice.Revoke(),
                      'public_keys': alice.PublicKeys(),
                      'decrypt': alice.Decrypt()}

    def create_policy(self,
                      bob_encrypting_key: bytes,
                      bob_verifying_key: bytes,
                      label: bytes,
                      m: int,
                      n: int,
                      expiration: maya.MayaDT,
                      value: int = None
                      ) -> dict:

        from nucypher.characters.lawful import Bob
        bob = Bob.from_public_keys(encrypting_key=bob_encrypting_key,
                                   verifying_key=bob_verifying_key)

        new_policy = self.character.create_policy(
            bob=bob,
            label=label,
            m=m,
            n=n,
            expiration=expiration,
            value=value
        )
        response_data = {'label': new_policy.label, 'policy_encrypting_key': new_policy.public_key}
        return response_data

    def derive_policy_encrypting_key(self, label: bytes) -> dict:
        policy_encrypting_key = self.character.get_policy_encrypting_key_from_label(label)
        response_data = {'policy_encrypting_key': policy_encrypting_key, 'label': label}
        return response_data

    def grant(self,
              bob_encrypting_key: bytes,
              bob_verifying_key: bytes,
              label: bytes,
              m: int,
              n: int,
              expiration: maya.MayaDT,
              value: int = None,
              rate: int = None,
              first_period_reward: int = None,
              ) -> dict:

        from nucypher.characters.lawful import Bob
        bob = Bob.from_public_keys(encrypting_key=bob_encrypting_key,
                                   verifying_key=bob_verifying_key)

        new_policy = self.character.grant(bob=bob,
                                          label=label,
                                          m=m,
                                          n=n,
                                          value=value,
                                          rate=rate,
                                          expiration=expiration)

        response_data = {'treasure_map': new_policy.treasure_map,
                         'policy_encrypting_key': new_policy.public_key,
                         'alice_verifying_key': new_policy.alice.stamp}
        return response_data

    def revoke(self, label: bytes, bob_verifying_key: bytes) -> dict:

        # TODO: Move deeper into characters
        policy_id = construct_policy_id(label, bob_verifying_key)
        policy = self.character.active_policies[policy_id]

        failed_revocations = self.character.revoke(policy)
        if len(failed_revocations) > 0:
            for node_id, attempt in failed_revocations.items():
                revocation, fail_reason = attempt
                if fail_reason == NotFound:
                    del(failed_revocations[node_id])
        if len(failed_revocations) <= (policy.n - policy.treasure_map.m + 1):
            del(self.character.active_policies[policy_id])

        response_data = {'failed_revocations': len(failed_revocations)}
        return response_data

    def decrypt(self, label: bytes, message_kit: bytes) -> dict:
        """
        Character control endpoint to allow Alice to decrypt her own data.
        """

        from nucypher.characters.lawful import Enrico
        policy_encrypting_key = self.character.get_policy_encrypting_key_from_label(label)

        # TODO #846: May raise UnknownOpenSSLError and InvalidTag.
        message_kit = UmbralMessageKit.from_bytes(message_kit)

        data_source = Enrico.from_public_keys(
            verifying_key=message_kit.sender_verifying_key,
            policy_encrypting_key=policy_encrypting_key,
            label=label
        )

        plaintexts = self.alice.decrypt_message_kit(
            message_kit=message_kit,
            data_source=data_source,
            label=label
        )

        response = {'cleartexts': plaintexts}
        return response

    def public_keys(self) -> dict:
        """
        Character control endpoint for getting Alice's public keys.
        """
        verifying_key = self.character.public_keys(SigningPower)
        response_data = {'alice_verifying_key': verifying_key}
        return response_data


class BobInterface(CharacterPublicInterface):

    specifications = {'join_policy': bob.JoinPolicy(),
                      'retrieve': bob.Retrieve(),
                      'public_keys': bob.PublicKeys()}

    def join_policy(self, label: bytes, alice_verifying_key: bytes):
        """
        Character control endpoint for joining a policy on the network.
        """
        self.character.join_policy(label=label, alice_verifying_key=alice_verifying_key)
        response = {'policy_encrypting_key': 'OK'}  # FIXME
        return response

    def retrieve(self,
                 label: bytes,
                 policy_encrypting_key: bytes,
                 alice_verifying_key: bytes,
                 message_kit: bytes):
        """
        Character control endpoint for re-encrypting and decrypting policy data.
        """
        from nucypher.characters.lawful import Enrico

        policy_encrypting_key = UmbralPublicKey.from_bytes(policy_encrypting_key)
        alice_verifying_key = UmbralPublicKey.from_bytes(alice_verifying_key)
        message_kit = UmbralMessageKit.from_bytes(message_kit)  # TODO #846: May raise UnknownOpenSSLError and InvalidTag.

        data_source = Enrico.from_public_keys(verifying_key=message_kit.sender_verifying_key,
                                              policy_encrypting_key=policy_encrypting_key,
                                              label=label)

        self.character.join_policy(label=label, alice_verifying_key=alice_verifying_key)
        plaintexts = self.character.retrieve(message_kit=message_kit,
                                             data_source=data_source,
                                             alice_verifying_key=alice_verifying_key,
                                             label=label)

        response_data = {'cleartexts': plaintexts}
        return response_data

    def public_keys(self):
        """
        Character control endpoint for getting Bob's encrypting and signing public keys
        """
        verifying_key = self.character.public_keys(SigningPower)
        encrypting_key = self.character.public_keys(DecryptingPower)
        response_data = {'bob_encrypting_key': encrypting_key, 'bob_verifying_key': verifying_key}
        return response_data


class EnricoInterface(CharacterPublicInterface):

    specifications = {'encrypt_message': enrico.EncryptMessage()}

    def encrypt_message(self, message: str):
        """
        Character control endpoint for encrypting data for a policy and
        receiving the messagekit (and signature) to give to Bob.
        """
        message_kit, signature = self.character.encrypt_message(bytes(message, encoding='utf-8'))
        response_data = {'message_kit': message_kit, 'signature': signature}
        return response_data
