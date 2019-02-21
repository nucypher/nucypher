from typing import Tuple, Callable

import click
import maya
from hendrix.deploy.base import HendrixDeploy
from umbral.keys import UmbralPublicKey

from nucypher.characters.control.base import CharacterControlSpecification
from nucypher.characters.control.serializers import AliceCharacterControlJsonSerializer, \
    BobCharacterControlJSONSerializer
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import DecryptingPower, SigningPower


def bytes_interface(func) -> Callable:
    """Manage protocol I/O validation and serialization"""

    def wrapped(instance, request, *args, **kwargs) -> bytes:

        # Read
        interface_name = func.__name__
        input_specification, output_specification = instance.get_specifications(interface_name=interface_name)
        request_data = instance.read(request_payload=request, input_specification=input_specification)

        # Inner Call
        response_data = func(instance, request_data, *args, **kwargs)

        # Write
        response_bytes = instance.write(response_data=response_data, output_specification=output_specification)

        return response_bytes
    return wrapped


class AliceControl(CharacterControlSpecification):

    __create_policy = (('bob_encrypting_key', 'bob_verifying_key', 'm', 'n', 'label'),  # In
                       ('label', 'policy_encrypting_key'))                              # Out

    __derive_policy = (('label', ),                 # In
                       ('policy_encrypting_key',))  # Out

    __grant = (('bob_encrypting_key', 'bob_verifying_key', 'm', 'n', 'label', 'expiration'),   # In
               ('treasure_map', 'policy_encrypting_key', 'alice_signing_key', 'label'))        # Out

    # TODO: Implement Revoke Spec
    __revoke = ((),  # In
                ())  # Out

    specifications = {'create_policy': __create_policy,  # type: Tuple[Tuple[str]]
                      'derive_policy': __derive_policy,
                      'grant': __grant,
                      'revoke': __revoke}

    def __init__(self, alice, *args, **kwargs):
        self.alice = alice
        super().__init__(*args, **kwargs)

    def run(self,  http_port: int, dry_run: bool = False):
        # Alice Control
        alice_control = self.alice.make_wsgi_app()
        click.secho("Starting Alice Character Control...")

        click.secho(f"Alice Verifying Key {bytes(self.alice.stamp).hex()}", fg="green", bold=True)

        # Run
        if dry_run:
            return

        hx_deployer = HendrixDeploy(action="start", options={"wsgi": alice_control, "http_port": http_port})
        hx_deployer.run()  # <--- Blocking Call to Reactor

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
        new_policy = self.alice.create_policy(bob, label, m, n, federated=federated_only)
        response_data = {'label': new_policy.label, 'policy_encrypting_key': new_policy.public_key}
        return response_data

    def derive_policy(self, label: bytes) -> dict:
        policy_encrypting_key = self.alice.get_policy_pubkey_from_label(label)
        response_data = {'policy_encrypting_key': policy_encrypting_key, 'label': label}
        return response_data

    def grant(self,
              bob_encrypting_key: bytes,
              bob_verifying_key: bytes,
              label: bytes,
              m: int,
              n: int,
              expiration: maya.MayaDT,
              federated_only: bool = True # TODO: Default for now
              ) -> dict:
        from nucypher.characters.lawful import Bob

        # Operate
        bob = Bob.from_public_keys({DecryptingPower: bob_encrypting_key,
                                    SigningPower: bob_verifying_key},
                                   federated_only=federated_only)

        new_policy = self.alice.grant(bob, label, m=m, n=n, expiration=expiration)

        response_data = {'treasure_map': new_policy.treasure_map,
                         'policy_encrypting_key': new_policy.public_key,
                         'alice_signing_key': new_policy.alice.stamp,
                         'label': new_policy.label}

        return response_data


class BobControl(CharacterControlSpecification):

    __join_policy = (('label', 'alice_signing_key'),
                     ('policy_encrypting_key', ))

    __retrieve = (('label', 'policy_encrypting_key', 'alice_signing_key', 'message_kit'),
                  ('plaintexts', ))

    __public_keys = ((),
                     ('bob_encrypting_key', 'bob_verifying_key'))

    specifications = {'join_policy': __join_policy,
                      'retrieve': __retrieve,
                      'public_keys': __public_keys}

    def __init__(self, bob, *args, **kwargs):
        self.bob = bob
        super().__init__(*args, **kwargs)

    def join_policy(self, label: bytes, alice_signing_key: bytes):
        """
        Character control endpoint for joining a policy on the network.
        """
        self.bob.join_policy(label=label, alice_pubkey_sig=alice_signing_key)
        response = dict()  # {'policy_encrypting_key': ''}  # FIXME
        return response

    def retrieve(self,
                 label: bytes,
                 policy_encrypting_key: bytes,
                 alice_signing_key: bytes,
                 message_kit: bytes):
        """
        Character control endpoint for re-encrypting and decrypting policy data.
        """
        from nucypher.characters.lawful import Enrico

        policy_encrypting_key = UmbralPublicKey.from_bytes(policy_encrypting_key)
        alice_pubkey_sig = UmbralPublicKey.from_bytes(alice_signing_key)
        message_kit = UmbralMessageKit.from_bytes(message_kit)  # TODO: May raise UnknownOpenSSLError and InvalidTag.

        data_source = Enrico.from_public_keys({SigningPower: message_kit.sender_pubkey_sig},
                                              policy_encrypting_key=policy_encrypting_key,
                                              label=label)

        self.bob.join_policy(label=label, alice_pubkey_sig=alice_pubkey_sig)
        plaintexts = self.bob.retrieve(message_kit=message_kit,
                                       data_source=data_source,
                                       alice_verifying_key=alice_pubkey_sig,
                                       label=label)

        response_data = {'plaintexts': plaintexts}
        return response_data

    def public_keys(self):
        """
        Character control endpoint for getting Bob's encrypting and signing public keys
        """
        verifying_key = self.bob.public_keys(SigningPower)
        encrypting_key = self.bob.public_keys(DecryptingPower)
        response_data = {'bob_encrypting_key': encrypting_key, 'bob_verifying_key': verifying_key}
        return response_data


class AliceJSONControl(AliceControl, AliceCharacterControlJsonSerializer):

    def create_policy(self, request):
        federated_only = True  # TODO: const for now
        result = super().create_policy(**self.load_create_policy_input(request=request), federated_only=federated_only)
        response_data = self.dump_create_policy_output(response=result)
        return response_data

    def derive_policy(self, request, label: str):
        label_bytes = label.encode()
        result = super().derive_policy(label=label_bytes)
        response_data = self.dump_derive_policy_output(response=result)
        return response_data

    def grant(self, request):
        result = super().grant(**self.parse_grant_input(request=request))
        response_data = self.dump_grant_output(response=result)
        return response_data


class AliceJSONBytesControl(AliceJSONControl, AliceCharacterControlJsonSerializer):

    @bytes_interface
    def create_policy(self, request):
        return super().create_policy(request=request)

    @bytes_interface
    def derive_policy(self, request, label: str):
        return super().derive_policy(request=request, label=label)

    @bytes_interface
    def grant(self, request):
        return super().grant(request=request)


class BobJSONControl(BobControl, BobCharacterControlJSONSerializer):

    def join_policy(self, request):
        """
        Character control endpoint for joining a policy on the network.
        """
        _result = super().join_policy(**self.load_join_policy_input(request=request))
        response = {'policy_encrypting_key': 'OK'}  # FIXME
        return response

    def retrieve(self, request):
        """
        Character control endpoint for re-encrypting and decrypting policy data.
        """
        result = super().retrieve(**self.load_retrieve_input(request=request))
        response_data = self.dump_retrieve_output(response=result)
        return response_data

    def public_keys(self, request):
        """
        Character control endpoint for getting Bob's encrypting and signing public keys
        """
        result = super().public_keys()
        response_data = self.dump_public_keys_output(response=result)
        return response_data


class BobJSONBytesControl(BobJSONControl, BobCharacterControlJSONSerializer):

    @bytes_interface
    def join_policy(self, request):
        """
        Character control endpoint for joining a policy on the network.
        """
        return super().join_policy(request=request)

    @bytes_interface
    def retrieve(self, request):
        """
        Character control endpoint for re-encrypting and decrypting policy data.
        """
        return super().retrieve(request=request)

    @bytes_interface
    def public_keys(self, request):
        """
        Character control endpoint for getting Bob's encrypting and signing public keys
        """
        return super().public_keys(request=request)
