#!/usr/local/bin/python3

import os
import sys
import json
import struct
import traceback
import logging

from click.exceptions import BadParameter
from click.testing import CliRunner
from nucypher.cli.main import nucypher_cli
from nucypher.config.constants import USER_LOG_DIR

log_file = LOG_PATH = os.path.join(USER_LOG_DIR, f'native-messaging.log')
logging.basicConfig(filename=log_file, filemode='w')


def get_message():
    message_length = sys.stdin.buffer.read(4)
    if len(message_length) == 0:
        sys.exit(0)
    messageLength = struct.unpack('@I', message_length)[0]
    message = sys.stdin.buffer.read(messageLength).decode('utf-8')
    return json.loads(message)


def encode_message(message):
    """Encode a message for transmission, given its content. """
    encodedContent = json.dumps(message).encode('utf-8')
    encodedLength = struct.pack('@I', len(encodedContent))
    return {'length': encodedLength, 'content': encodedContent}


# Send an encoded message to stdout
def send_message(message):
    sys.stdout.buffer.write(message['length'])
    sys.stdout.buffer.write(message['content'])
    sys.stdout.buffer.flush()


click_runner = CliRunner()  # TODO: Make Proper

try:
    while True:
        command_data = get_message()  # < -------- REQUEST FROM BROWSER
        action = command_data['action']
        character = command_data.get('character', '')
        options = []

        if character:
            options.append(character)
        options.append(action)
        #  if there is no password, the process will just hang
        #  so lets deal with that now.

        route_key = '.'.join(options)
        try:
            NUCYPHER_KEYRING_PASSWORD = command_data['keyring_password']
        except KeyError:
            output = {
                "input": command_data,
                "result": None,
                "error": "keyring password is required",
                "route": route_key,
            }
            send_message(encode_message(output))
        else:
            options.append('--json-ipc')

            if command_data.get("options"):
                options.append('--options')

            for param, value in command_data['args'].items():
                param = param.replace("_", "-")
                if value is True:
                    options.append(f"--{param}")
                else:
                    options.extend((f"--{param}", value))

            ####
            # INTERNAL INTERFACE
            logging.error(f"calling NuCypher CLI with {NUCYPHER_KEYRING_PASSWORD}")
            environ = {'NUCYPHER_KEYRING_PASSWORD': NUCYPHER_KEYRING_PASSWORD}
            result = None
            try:
                nc_result = click_runner.invoke(nucypher_cli, options, catch_exceptions=True, env=environ)
                logging.error(f"result is: {nc_result.output}")
                result = nc_result.output
            except BadParameter as e:
                logging.error(f"NuCypher CLI error ==== \n {'.'.join(dir(e).keys())}")

                exc_type, exc_value, exc_traceback = sys.exc_info()
                lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                err = ''.join('\n'+line for line in lines)  # Log it or whatever here
                logging.error(f"NuCypher CLI error ==== \n {err}")
            ####

            del command_data['keyring_password']
            output = {
                "input": command_data,
                "route": route_key,
                "result": result,
            }
            final_message = encode_message(output)
            logging.error(f"Sending to the browser: {final_message}")
            send_message(final_message)  # < ---- RESPONSE TO BROWSER

except Exception:
    exc_type, exc_value, exc_traceback = sys.exc_info()
    lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    err = ''.join('\n'+line for line in lines)  # Log it or whatever here
    logging.error(f"ERROR ============= \n {err}")
