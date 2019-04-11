import functools

import maya
from umbral.keys import UmbralPublicKey

from nucypher.characters.control.specifications import AliceSpecification, BobSpecification, EnricoSpecification
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import DecryptingPower, SigningPower
from nucypher.crypto.utils import construct_policy_id
from nucypher.network.middleware import NotFound


def character_control_interface(func):

    # noinspection PyPackageRequirements
    @functools.wraps(func)
    def wrapped(instance, request=None, *args, **kwargs) -> bytes:

        # Record request time
        received = maya.now()

        # Get specification
        interface_name = func.__name__
        input_specification, output_specification = instance.get_specifications(interface_name=interface_name)

        if request and instance.serialize:

            # Serialize request
            if instance.serialize:
                request = instance.serializer(data=request, specification=input_specification)

            # Validate request
            instance.validate_request(request=request, interface_name=interface_name)

        # Call the interface
        response = func(self=instance, request=request, *args, **kwargs)

        # Validate response
        instance.validate_response(response=response, interface_name=interface_name)

        # Record duration
        responding = maya.now()
        duration = responding - received

        # Assemble response with metadata
        response_with_metadata = instance.serializer.build_response_metadata(response=response, duration=duration)

        # Emit
        return instance.emitter(response=response_with_metadata)

    return wrapped


class CharacterPublicInterface:

    def __init__(self, character=None, *args, **kwargs):
        self.character = character
        super().__init__(*args, **kwargs)


class AliceInterface(CharacterPublicInterface, AliceSpecification):

    def __init__(self, alice, *args, **kwargs):
        self.alice = alice
        super().__init__(character=alice, *args, **kwargs)

    def create_policy(self,
                      bob_encrypting_key: bytes,
                      bob_verifying_key: bytes,
                      label: bytes,
                      m: int,
                      n: int,
                      federated_only: bool = True,  # TODO: Default for now
                      ) -> dict:

        from nucypher.characters.lawful import Bob

        crypto_powers = {DecryptingPower: bob_encrypting_key, SigningPower: bob_verifying_key}
        bob = Bob.from_public_keys(crypto_powers, federated_only=federated_only)
        new_policy = self.character.create_policy(bob, label, m, n, federated=federated_only)
        response_data = {'label': new_policy.label, 'policy_encrypting_key': new_policy.public_key}
        return response_data

    def derive_policy_encrypting_key(self, label: bytes) -> dict:
        policy_encrypting_key = self.character.get_policy_pubkey_from_label(label)
        response_data = {'policy_encrypting_key': policy_encrypting_key, 'label': label}
        return response_data

    def grant(self,
              bob_encrypting_key: bytes,
              bob_verifying_key: bytes,
              label: bytes,
              m: int,
              n: int,
              expiration: maya.MayaDT,
              federated_only: bool = True  # TODO: Default for now
              ) -> dict:
        from nucypher.characters.lawful import Bob

        # Operate
        bob = Bob.from_public_keys({DecryptingPower: bob_encrypting_key,
                                    SigningPower: bob_verifying_key},
                                   federated_only=federated_only)

        new_policy = self.character.grant(bob, label, m=m, n=n, expiration=expiration)

        response_data = {'treasure_map': new_policy.treasure_map,
                         'policy_encrypting_key': new_policy.public_key,
                         'alice_verifying_key': new_policy.alice.stamp}
        return response_data

    def revoke(self, label: bytes, bob_verifying_key: bytes):
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

    def public_keys(self):
        """
        Character control endpoint for getting Alice's public keys.
        """
        verifying_key = self.alice.public_keys(SigningPower)
        response_data = {'alice_verifying_key': verifying_key}
        return response_data


class BobInterface(CharacterPublicInterface, BobSpecification):

    def __init__(self, bob, *args, **kwargs):
        self.bob = bob
        super().__init__(*args, **kwargs)

    def join_policy(self, label: bytes, alice_verifying_key: bytes):
        """
        Character control endpoint for joining a policy on the network.
        """
        self.bob.join_policy(label=label, alice_pubkey_sig=alice_verifying_key)
        response = dict()  # {'policy_encrypting_key': ''}  # FIXME
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
        alice_pubkey_sig = UmbralPublicKey.from_bytes(alice_verifying_key)
        message_kit = UmbralMessageKit.from_bytes(message_kit)  # TODO #846: May raise UnknownOpenSSLError and InvalidTag.

        data_source = Enrico.from_public_keys({SigningPower: message_kit.sender_pubkey_sig},
                                              policy_encrypting_key=policy_encrypting_key,
                                              label=label)

        self.bob.join_policy(label=label, alice_pubkey_sig=alice_pubkey_sig)
        plaintexts = self.bob.retrieve(message_kit=message_kit,
                                       data_source=data_source,
                                       alice_verifying_key=alice_pubkey_sig,
                                       label=label)

        response_data = {'cleartexts': plaintexts}
        return response_data

    def public_keys(self):
        """
        Character control endpoint for getting Bob's encrypting and signing public keys
        """
        verifying_key = self.bob.public_keys(SigningPower)
        encrypting_key = self.bob.public_keys(DecryptingPower)
        response_data = {'bob_encrypting_key': encrypting_key, 'bob_verifying_key': verifying_key}
        return response_data


class EnricoInterface(CharacterPublicInterface, EnricoSpecification):

    def __init__(self, enrico, *args, **kwargs):
        self.enrico = enrico
        super().__init__(*args, **kwargs)

    def encrypt_message(self, message: str):
        """
        Character control endpoint for encrypting data for a policy and
        receiving the messagekit (and signature) to give to Bob.
        """
        message_kit, signature = self.enrico.encrypt_message(bytes(message, encoding='utf-8'))
        response_data = {'message_kit': message_kit, 'signature': signature}
        return response_data

