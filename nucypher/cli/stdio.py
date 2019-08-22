#!/usr/local/bin/python3

import os
import sys
import json
import struct
import traceback
import logging

from nucypher.characters.control.specifications import ALL_SPECIFICATIONS

lookup = {spec._name: spec for spec in ALL_SPECIFICATIONS}

log_path = os.path.dirname(os.path.realpath(__file__))
log_file = log_path + '/err.log'
logging.basicConfig(filename=log_file, filemode='w')


def getMessage():
    rawLength = sys.stdin.buffer.read(4)
    if len(rawLength) == 0:
        sys.exit(0)
    messageLength = struct.unpack('@I', rawLength)[0]
    message = sys.stdin.buffer.read(messageLength).decode('utf-8')
    return json.loads(message)

# Encode a message for transmission,
# given its content.
def encodeMessage(messageContent):
    encodedContent = json.dumps(messageContent).encode('utf-8')
    encodedLength = struct.pack('@I', len(encodedContent))
    return {'length': encodedLength, 'content': encodedContent}

# Send an encoded message to stdout
def sendMessage(encodedMessage):
    sys.stdout.buffer.write(encodedMessage['length'])
    sys.stdout.buffer.write(encodedMessage['content'])
    sys.stdout.buffer.flush()


try:
    while True:
        command_data = getMessage()
        specification = lookup[command_data['character']._specifications[command_data['action']]
        sendMessage(encodeMessage(receivedMessage))

except Exception:
    exc_type, exc_value, exc_traceback = sys.exc_info()
    lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    err = ''.join('!! ' + line for line in lines)  # Log it or whatever here
    logging.error(err)
