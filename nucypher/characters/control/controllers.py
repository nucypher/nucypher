import functools

import click
import maya
from hendrix.deploy.base import HendrixDeploy
from umbral.keys import UmbralPublicKey

from nucypher.characters.control.specifications import AliceSpecification, BobSpecification
from nucypher.characters.control.serializers import AliceCharacterControlJsonSerializer, \
    BobCharacterControlJSONSerializer
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import DecryptingPower, SigningPower


def character_control_interface(func):
    """Validate I/O specification for dictionary character control interfaces"""

    @functools.wraps(func)
    def wrapped(instance, request=None, *args, **kwargs) -> bytes:

        # Get specification
        input_specification, output_specification = instance.get_specifications(interface_name=func.__name__)

        # Read bytes
        if instance.as_bytes is True:
            request = instance._read(request_payload=request)

        # Validate request body (if there is one)
        if request:
            instance.validate_input(request_data=request, input_specification=input_specification)

        # Call the interface
        response = func(self=instance, request=request, *args, **kwargs)

        # Build Response and Validate
        response = instance._build_response(response_data=response)
        instance.validate_output(response_data=response, output_specification=output_specification)

        # Write bytes
        if instance.as_bytes is True:
            response = instance._write(response_data=response, output_specification=output_specification)

        # Respond
        return response
    return wrapped


class WSGICharacterController:

    def __init__(self, character=None, as_bytes: bool = False, *args, **kwargs):
        self.character = character
        self.as_bytes = as_bytes
        super().__init__(*args, **kwargs)

    def start_wsgi_controller(self, http_port: int, dry_run: bool = False):

        character_wsgi_control = self.character.make_wsgi_app()
        click.secho("Starting HTTP Character Control...")

        if dry_run:
            return

        hx_deployer = HendrixDeploy(action="start", options={"wsgi": character_wsgi_control, "http_port": http_port})
        hx_deployer.run()  # <--- Blocking Call to Reactor


class AliceControl(WSGICharacterController, AliceSpecification):

    def __init__(self, alice, *args, **kwargs):
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

    def derive_policy(self, label: bytes) -> dict:
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
                         'alice_signing_key': new_policy.alice.stamp,
                         'label': new_policy.label}

        return response_data


class BobControl(WSGICharacterController, BobSpecification):

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

    @character_control_interface
    def create_policy(self, request):
        federated_only = True  # TODO: const for now
        result = super().create_policy(**self.load_create_policy_input(request=request), federated_only=federated_only)
        response_data = self.dump_create_policy_output(response=result)
        return response_data

    @character_control_interface
    def derive_policy(self, label: str, request=None):
        label_bytes = label.encode()
        result = super().derive_policy(label=label_bytes)
        response_data = self.dump_derive_policy_output(response=result)
        return response_data

    @character_control_interface
    def grant(self, request):
        result = super().grant(**self.parse_grant_input(request=request))
        response_data = self.dump_grant_output(response=result)
        return response_data


class BobJSONControl(BobControl, BobCharacterControlJSONSerializer):

    @character_control_interface
    def join_policy(self, request):
        """
        Character control endpoint for joining a policy on the network.
        """
        _result = super().join_policy(**self.load_join_policy_input(request=request))
        response = {'policy_encrypting_key': 'OK'}  # FIXME
        return response

    @character_control_interface
    def retrieve(self, request):
        """
        Character control endpoint for re-encrypting and decrypting policy data.
        """
        result = super().retrieve(**self.load_retrieve_input(request=request))
        response_data = self.dump_retrieve_output(response=result)
        return response_data

    @character_control_interface
    def public_keys(self, request):
        """
        Character control endpoint for getting Bob's encrypting and signing public keys
        """
        result = super().public_keys()
        response_data = self.dump_public_keys_output(response=result)
        return response_data
