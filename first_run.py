#!/usr/bin/env python3


if __name__ == '__main__':
    import sys
    import base64
    from nkms.config import utils
    from nkms.crypto import api as API

    print("Welcome to NuCypher KMS!")
    print("The first-run script will take you through key generation and node creation.")

    config = utils.read_config()

    # Generate the keys
    print("Generating keys...")

    # Encryption keys
    ecies_privkey = API.ecies_gen_priv(to_bytes=True)
    ecies_pubkey = API.ecies_priv2pub(ecies_privkey, to_bytes=True)

    # Signing keys
    ecdsa_privkey = API.ecdsa_gen_priv()
    ecdsa_pubkey = API.ecdsa_priv2pub(ecdsa_privkey, to_bytes=True)

    # Encode the keys as base64
    keyfile_data = ecies_privkey + ecies_pubkey + ecdsa_privkey + ecdsa_pubkey
    keyfile_data = base64.b64encode(keyfile_data)

    # Write to keyfile, if empty
    # TODO: Encrypt the private keys
    keyfile_path = config['owner_key']['keyfile']
    with open(keyfile_path, 'w+') as f:
        f.seek(0)
        check_byte = f.read(1)
        if check_byte != '':
            print("ERROR: Keyfile is not empty! Check your keyfile path.")
            sys.exit()
        f.seek(0)
        f.write(keyfile_data.decode())
    print("Keys generated and written to keyfile!")

    # TODO: Add config script stuff for running a re-encrypting node or
    #       generating a policy.
    print("First run complete! Thanks for using NuCypher!")
    sys.exit()
