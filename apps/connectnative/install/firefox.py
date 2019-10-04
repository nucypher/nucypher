import platform
import os
import shutil
import json
from os.path import expanduser

EXTENSION_DATA = {
  "name": "nucypher",
  "description": "Native messaging client for Nucypher",
  "path": None,
  "type": "stdio",
  "allowed_extensions": [ "nucypher@nucypher.com" ]
}

FILE_LOCATIONS = {
    "Linux": [
        '.mozilla/native-messaging-hosts/',
        '.mozilla/managed-storage/',
        '.mozilla/pkcs11-modules/',
    ],
    "Darwin": [
        'Library/Application Support/Mozilla/NativeMessagingHosts/',
        'Library/Application Support/Mozilla/ManagedStorage/',
        'Library/Application Support/Mozilla/PKCS11Modules/',
    ]
}

def install():
    this_os = platform.system()
    home = expanduser("~")

    stdio_cli = shutil.which('nucypher-stdio-receiver')
    if not stdio_cli:
        raise NotImplementedError(
            "Can't find stdio executable.  You need to run a `pip install .` to install the cli "
            "executable needed to run this extension (look in setup.py)"
        )
    install_data = EXTENSION_DATA
    install_data['path'] = stdio_cli

    for dest in FILE_LOCATIONS[this_os]:
        location = os.path.join(home, dest, 'nucypher.json')
        os.makedirs(os.path.dirname(location), exist_ok=True)
        with open(location, 'w') as outfile:
            json.dump(install_data, outfile)
            print (f"wrote extension data to {location}...")

if __name__ == '__main__':
    install()
