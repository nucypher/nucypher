import json
import os
from base64 import b64encode

from twisted.logger import Logger

from nucypher.characters.control.emitters import JSONRPCStdoutEmitter
from nucypher.characters.lawful import Ursula
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import BobConfiguration
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import SigningPower
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD, TEMPORARY_DOMAIN

log = Logger()


def test_bob_cannot_init_with_dev_flag(click_runner):
    init_args = ('bob', 'init',
                 '--federated-only',
                 '--dev')
    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False)
    assert result.exit_code == 2
    assert 'Cannot create a persistent development character' in result.output, 'Missing or invalid error message was produced.'


def test_bob_retrieves_twice_via_cli(click_runner,
                                     capsule_side_channel,
                                     enacted_federated_policy,
                                     federated_ursulas,
                                     custom_filepath_2,
                                     federated_alice
                                     ):
    teacher = list(federated_ursulas)[0]

    first_message = capsule_side_channel.reset(plaintext_passthrough=True)
    three_message_kits = [capsule_side_channel(), capsule_side_channel(), capsule_side_channel()]

    bob_config_root = custom_filepath_2
    bob_configuration_file_location = os.path.join(bob_config_root, BobConfiguration.generate_filename())
    label = enacted_federated_policy.label

    # I already have a Bob.

    # Need to init so that the config file is made, even though we won't use this Bob.
    bob_init_args = ('bob', 'init',
                     '--network', TEMPORARY_DOMAIN,
                     '--config-root', bob_config_root,
                     '--federated-only')

    envvars = {'NUCYPHER_KEYRING_PASSWORD': INSECURE_DEVELOPMENT_PASSWORD}

    log.info("Init'ing a normal Bob; we'll substitute the Policy Bob in shortly.")
    bob_init_response = click_runner.invoke(nucypher_cli, bob_init_args, catch_exceptions=False, env=envvars)

    message_kit_bytes = bytes(three_message_kits[0])
    message_kit_b64_bytes = b64encode(message_kit_bytes)
    UmbralMessageKit.from_bytes(message_kit_bytes)

    retrieve_args = ('bob', 'retrieve',
                     '--mock-networking',
                     '--json-ipc',
                     '--teacher', teacher.seed_node_metadata(as_teacher_uri=True),
                     '--config-file', bob_configuration_file_location,
                     '--message-kit', message_kit_b64_bytes,
                     '--label', label,
                     '--policy-encrypting-key', federated_alice.get_policy_encrypting_key_from_label(label).hex(),
                     '--alice-verifying-key', federated_alice.public_keys(SigningPower).hex()
                     )

    from nucypher.cli import actions

    def substitute_bob(*args, **kwargs):
        log.info("Substituting the Policy's Bob in CLI runtime.")
        this_fuckin_guy = enacted_federated_policy.bob
        somebody_else = Ursula.from_teacher_uri(teacher_uri=kwargs['teacher_uri'],
                                                min_stake=0,
                                                federated_only=True,
                                                network_middleware=this_fuckin_guy.network_middleware)
        this_fuckin_guy.remember_node(somebody_else)
        this_fuckin_guy.controller.emitter = JSONRPCStdoutEmitter()
        return this_fuckin_guy

    _old_make_character_function = actions.make_cli_character
    try:
        log.info("Patching make_cli_character with substitute_bob")
        actions.make_cli_character = substitute_bob

        # Once...
        retrieve_response = click_runner.invoke(nucypher_cli, retrieve_args, catch_exceptions=False, env=envvars)
        log.info(f"First retrieval response: {retrieve_response.output}")
        assert retrieve_response.exit_code == 0

        retrieve_response = json.loads(retrieve_response.output)
        for cleartext in retrieve_response['result']['cleartexts']:
            assert cleartext.encode() == capsule_side_channel.plaintexts[1]

        # and again!
        retrieve_response = click_runner.invoke(nucypher_cli, retrieve_args, catch_exceptions=False, env=envvars)
        log.info(f"Second retrieval response: {retrieve_response.output}")
        assert retrieve_response.exit_code == 0

        retrieve_response = json.loads(retrieve_response.output)
        for cleartext in retrieve_response['result']['cleartexts']:
            assert cleartext.encode() == capsule_side_channel.plaintexts[1]
    finally:
        log.info("un-patching make_cli_character")
        actions.make_cli_character = _old_make_character_function
